import os
import httpx
import logging
import json
import calendar
from uuid import UUID
from enum import Enum, IntEnum
from time import localtime, mktime
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pandas import DateOffset
from async_lru import alru_cache
from dotenv import load_dotenv
from fastapi import HTTPException
from itertools import groupby
from tortoise.functions import Sum
from tortoise.models import Model
from tortoise.exceptions import FieldError, IntegrityError
from tortoise.expressions import RawSQL, Q, Function
from pypika import CustomFunction
from pydantic import TypeAdapter
from app.ynab.models import AccountsResponse, CategoriesResponse, MonthDetailResponse, MonthSummariesResponse, PayeesResponse, \
    TransactionsResponse, Account, Category, MonthSummary, MonthDetail, Payee, TransactionDetail
from app.db.models import YnabServerKnowledge, YnabAccounts, YnabCategories, YnabMonthSummaries, YnabMonthDetailCategories, YnabPayees, \
    YnabTransactions
from app.enums import TransactionTypeOptions, FilterTypes
from app.ynab.schemas import AvailableBalanceResponse, CardBalancesResponse, CategorySpentResponse, CategorySpent, \
    CreditAccountResponse, EarnedVsSpentResponse, IncomeVsExpensesResponse, LastXTransactions, SpentInPeriodResponse, \
    SpentVsBudgetResponse, SubCategorySpentResponse, TotalSpentResponse, TransactionsByFilterResponse, TransactionsByMonthResponse

load_dotenv()
dotenv_ynab_url = os.getenv("EXT_YNAB_URL")
dotenv_ynab_token = os.getenv("EXT_YNAB_TOKEN")
dotenv_ynab_budget_id = os.getenv("YNAB_BUDGET_ID")

class YNAB():
    CAT_EXPENSE_NAMES = ['Frequent', 'Giving', 'Non-Monthly Expenses', 'Work']

    @classmethod
    async def available_balance(cls) -> AvailableBalanceResponse:
        db_queryset = YnabAccounts.annotate(
            available=Sum('balance'),
            spent=Sum(RawSQL('''CASE WHEN "type" != 'checking' THEN "balance" ELSE 0 END''')),
            total=Sum(RawSQL('''CASE WHEN "type" = 'checking' THEN "balance" ELSE 0 END'''))
        ).first().values('total','spent','available')
        
        db_result = await db_queryset

        logging.debug(f"DB Query: {db_queryset.sql()}")
        logging.debug(f"DB Result: {db_result}")

        return AvailableBalanceResponse(**db_result)
    
    @classmethod
    async def card_balances(cls) -> CardBalancesResponse:
        db_queryset = YnabAccounts.filter(
            type__not='checking'
        ).values('name','balance',cleared='cleared_balance',uncleared='uncleared_balance')
        
        db_result = await db_queryset

        logging.debug(f"DB Query: {db_queryset.sql()}")
        logging.debug(f"DB Result: {db_result}")

        return CardBalancesResponse(data=db_result)

    @classmethod
    async def categories_spent_db_q(cls,
        current_month: bool = None, 
        since_date: str = None, 
        year: Enum = None, 
        months: IntEnum = None,
        specific_month: Enum = None
        ) -> list[CategorySpent]:
        if current_month:
            db_queryset = YnabCategories.annotate(
                spent=Sum('activity'),
                budget=Sum('budgeted')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES
            ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')
        elif since_date and specific_month:
            db_queryset = YnabMonthDetailCategories.annotate(
                spent=Sum('activity'),
                budget=Sum('budgeted')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                month_summary_fk__month=since_date
            ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')    
        elif months:
            logging.debug(f"Returning category info for the months since: {since_date}.")
            db_queryset = YnabMonthDetailCategories.annotate(
                spent=Sum('activity'),
                budget=Sum('budgeted')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                month_summary_fk__month__gte=since_date
            ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')
        elif year:
            logging.debug(f"Returning category info for the year since: {year.value}.")
            db_queryset = YnabMonthDetailCategories.annotate(
                spent=Sum('activity'),
                budget=Sum('budgeted')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                month_summary_fk__month__year=year.value
            ).group_by('category_group_name').order_by('spent').values('spent','budget',name='category_group_name')            

        db_result = await db_queryset

        logging.debug(f"DB Query: {db_queryset.sql()}")
        logging.debug(f"DB Result: {db_result}")

        return db_result

    @classmethod
    async def categories_spent(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> CategorySpentResponse:
        since_date = await YnabHelpers.get_date_for_transactions(year=year, months=months, specific_month=specific_month)
        if year and specific_month:
            current_year_month = datetime.today().replace(day=1).strftime('%Y-%m-%d')
            if current_year_month == since_date:
                logging.debug("Returning current month category info.")
                db_result = await cls.categories_spent_db_q(current_month=True)
            else:
                logging.debug(f"Returning category info for the month starting: {since_date}.")
                db_result = await cls.categories_spent_db_q(since_date=since_date, specific_month=specific_month)
        else:
            # This will return both the full year, as well as the last X months.
            current_month = await cls.categories_spent_db_q(current_month=True)
            prev_months = await cls.categories_spent_db_q(since_date=since_date, months=months, year=year)

            db_result = []
            # Create a dictionary for fast lookup of values from prev_months
            dict_list = {item['name']: item for item in prev_months}

            # Iterate over list1 and update values with corresponding values from prev_months
            for category in current_month:
                db_result.append({
                    'name': category['name'],
                    'spent': category['spent'] + dict_list[category['name']]['spent'],
                    'budget': category['budget'] + dict_list[category['name']]['budget'],
                })

        return CategorySpentResponse(
            since_date=since_date,
            data=db_result
        )

    @classmethod
    async def earned_vs_spent_db_q(cls, since_date: str = None, end_date: str = None) -> dict:
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')

        db_queryset = YnabTransactions.annotate(
            earned=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            spent=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('deleted').values('earned','spent').sql()
        logging.debug(f"SQL Query: {db_queryset}")

        db_results = await YnabTransactions.annotate(
            earned=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            spent=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('deleted').values('earned','spent')
        
        if len(db_results) != 1:
            raise HTTPException(status_code=500, detail="More than one result returned.")

        return db_results[0]

    @classmethod
    async def earned_vs_spent(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> EarnedVsSpentResponse:        
        since_date = await YnabHelpers.get_date_for_transactions(year=year, months=months, specific_month=specific_month)
        if months:
            end_date = datetime.now()
        elif year and specific_month:
            # Set the date to the last day of the current month.
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date)
        elif year:
            # Set the date to the last day of the current year.
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date, year=True)

        db_results = await cls.earned_vs_spent_db_q(since_date=since_date, end_date=end_date)

        return EarnedVsSpentResponse(
            since_date=since_date,
            earned=db_results['earned'],
            spent=db_results['spent']
        )

    @classmethod
    async def income_vs_expenses_db_q(cls, since_date, year: Enum = None, specific_month: Enum = None) -> list[dict]:
        # From the since date, go through each month and add it to the data
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
        end_date = datetime.now()

        if specific_month:
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date)
        if year and not specific_month:
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date, year=True)

        db_queryset = YnabTransactions.annotate(
            total_amount=Sum('amount'),
            income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('date').values('date','total_amount','income','expense').sql()
        logging.debug(f"SQL Query: {db_queryset}")

        db_results = await YnabTransactions.annotate(
            total_amount=Sum('amount'),
            income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('date').values('date','total_amount','income','expense')
        
        # Example output of db_results
        # [{'date': datetime.date(2024, 1, 7), 'total_amount': 14427080.0, 'income': 21012910.0, 'expense': -6585830.0}]

        return db_results

    @classmethod
    async def income_vs_expenses(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> IncomeVsExpensesResponse:
        since_date = await YnabHelpers.get_date_for_transactions(year, months, specific_month)

        db_results = await cls.income_vs_expenses_db_q(since_date=since_date, specific_month=specific_month, year=year)

        # Function to extract year and month from a date
        def extract_year_month(entry):
            return entry['date'].year, entry['date'].month

        # Sort the list by year and month
        sorted_result = sorted(db_results, key=extract_year_month)

        # Group the sorted list by year and month
        grouped_result = {key: list(group) for key, group in groupby(sorted_result, key=extract_year_month)}

        result_json = []
        # Print or use the grouped result with total income and total expense
        for year_month, entries in grouped_result.items():
            year, month = year_month
            month_full_name = calendar.month_name[month] # January
            month_year = {
                'month': month_full_name,
                'year': str(year),
                'income': await YnabHelpers.convert_to_float(sum(entry['income'] for entry in entries)),
                'expenses': await YnabHelpers.convert_to_float(sum(entry['expense'] for entry in entries))
            }
            result_json.append(month_year)

        return IncomeVsExpensesResponse(
            since_date=since_date,
            data=result_json
        )

    @classmethod
    async def last_paid_date_for_accounts(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> CreditAccountResponse:
        # Look over the last month. If no payment, assume the bill has not been paid yet.
        since_date = await YnabHelpers.get_date_for_transactions(year=year, months=months, specific_month=specific_month)
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
        end_date = datetime.now()

        if specific_month:
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date)
        if year and not specific_month:
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date, year=True)

        db_queryset = YnabTransactions.filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(transfer_account_id__isnull=False),
            Q(account_name__not_in=["HSBC ADVANCE"])
        ).group_by('account_name', 'id').order_by('-date').values('id','date','amount','account_name').sql()
        logging.debug(f"SQL Query: {db_queryset}")

        db_results = await YnabTransactions.filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(transfer_account_id__isnull=False),
            Q(account_name__not_in=["HSBC ADVANCE"])
        ).group_by('account_name', 'id').order_by('-date').values('id','date','amount','account_name')
        # TODO might have an issue when more than one result is returned on the UI.

        return CreditAccountResponse(
            since_date=since_date,
            data=db_results
        )

    @classmethod
    async def last_x_transactions(cls, count: int, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> LastXTransactions:
        since_date = await YnabHelpers.get_date_for_transactions(year=year, months=months, specific_month=specific_month)
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
        
        # For year, or last x months - get the current date and the last X transactions
        if year or months:
            end_date = datetime.now()
        # For year and specific month - get the last date of that month and then the last x transactions
        if year and specific_month:
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date)

        db_queryset = YnabTransactions.filter(
            date__gte=since_date_dt,
            date__lte=end_date,
            category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES
        ).order_by('-date').limit(count).values('amount','date',subcategory='category_name',payee='payee_name').sql()
        logging.debug(f"SQL Query: {db_queryset}")

        db_results = await YnabTransactions.filter(
            date__gte=since_date_dt,
            date__lte=end_date,
            category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES
        ).order_by('-date').limit(count).values('amount','date',subcategory='category_name',payee='payee_name')

        return LastXTransactions(
            since_date=since_date,
            data=db_results
        )

    @classmethod #TODO
    async def spent_in_period(cls, period: Enum) -> SpentInPeriodResponse:
        # TODO add filters for whether I want to include bills or just things which do not come from a specific account (e.g. Current Account)
        match period.value:
            case 'TODAY':
                current_date = datetime.today().strftime('%Y-%m-%d')
                pydantic_transactions_list = await YnabHelpers.pydantic_transactions(since_date=current_date)
                
                total_spent = 0.0
                for transaction in pydantic_transactions_list:
                    if transaction.amount > 0: continue
                    total_spent += transaction.amount
                
                return SpentInPeriodResponse(
                    spent=await YnabHelpers.convert_to_float(total_spent)
                )
            case 'YESTERDAY':
                current_date = datetime.today() - DateOffset(days=1)
                current_date = current_date.strftime('%Y-%m-%d')
                pydantic_transactions_list = await YnabHelpers.pydantic_transactions(since_date=current_date)
                
                total_spent = 0.0
                for transaction in pydantic_transactions_list:
                    if transaction.amount > 0: continue
                    total_spent += transaction.amount
                
                return SpentInPeriodResponse(
                    spent=await YnabHelpers.convert_to_float(total_spent)
                )
            case 'THIS_WEEK':
                current_date = datetime.today()
                days_to_monday =  current_date.weekday() - 0
                current_date = datetime.today() - DateOffset(days=days_to_monday)
                current_date = current_date.strftime('%Y-%m-%d')
                pydantic_transactions_list = await YnabHelpers.pydantic_transactions(since_date=current_date)
                                
                total_spent = 0.0
                for transaction in pydantic_transactions_list:
                    if transaction.amount > 0 or transaction.category_name in ["Loans", "Monthly Bills", "Credit Card Payments", "Yearly Bills"]: continue
                    total_spent += transaction.amount
                
                return SpentInPeriodResponse(
                    spent=await YnabHelpers.convert_to_float(total_spent)
                )
            case 'LAST_WEEK':
                # TODO
                return None
            case _:
                return None

    @classmethod # TODO
    async def spent_vs_budget(cls) -> SpentVsBudgetResponse:
        pydantic_categories_list = await YnabHelpers.pydantic_categories()

        total_balance = 0.0 # Amount difference between whats been budgeted, and the activity.
        total_budgeted = 0.0 # Budget assigned to the category
        total_spent = 0.0
        # Only categories that I care about for tracking the monthly target.
        # This is usually when I only have a budget assigned to a category.
        # So I should skip any category which does not have a budget assigned.
        for category in pydantic_categories_list:
            if category.category_group_name not in cls.CAT_EXPENSE_NAMES: continue
            total_spent += category.activity
            total_balance += category.balance
            total_budgeted += category.budgeted
            logging.debug(f'''
            Category details:
                name: {category.name}
                activity: {category.activity}
                balance: {category.balance}
                budgeted: {category.budgeted}
            ''')

        logging.debug(f'''
        Total Spent: {total_spent}
        Total Budgeted: {total_budgeted}
        ''')

        return {
            'balance': await YnabHelpers.convert_to_float(total_balance),
            'budget': await YnabHelpers.convert_to_float(total_budgeted),
            'spent': await YnabHelpers.convert_to_float(-total_spent),
        }

    @classmethod
    async def sub_categories_spent_db_q(cls,
        current_month: bool = None, 
        since_date: str = None, 
        year: Enum = None, 
        months: IntEnum = None,
        specific_month: Enum = None
        ) -> list[CategorySpent]:
        if current_month:
            db_queryset = YnabCategories.annotate(
                spent=Sum('activity')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES
            ).group_by('category_group_name','name').order_by('spent').values('spent','name','category_group_name')
        elif since_date and specific_month:
            db_queryset = YnabMonthDetailCategories.annotate(
                spent=Sum('activity')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                month_summary_fk__month=since_date
            ).group_by('category_group_name','name').order_by('spent').values('spent','name','category_group_name')    
        elif months:
            logging.debug(f"Returning category info for the months since: {since_date}.")
            db_queryset = YnabMonthDetailCategories.annotate(
                spent=Sum('activity')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                month_summary_fk__month__gte=since_date
            ).group_by('category_group_name','name').order_by('spent').values('spent','name','category_group_name')
        elif year:
            logging.debug(f"Returning category info for the year since: {year.value}.")
            db_queryset = YnabMonthDetailCategories.annotate(
                spent=Sum('activity')
            ).filter(
                category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                month_summary_fk__month__year=year.value
            ).group_by('category_group_name','name').order_by('spent').values('spent','name','category_group_name')            

        db_result = await db_queryset

        logging.debug(f"DB Query: {db_queryset.sql()}")
        logging.debug(f"DB Result: {db_result}")

        return db_result

    @classmethod
    async def sub_categories_spent(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> SubCategorySpentResponse:
        since_date = await YnabHelpers.get_date_for_transactions(year=year, months=months, specific_month=specific_month)
        if year and specific_month:
            current_year_month = datetime.today().replace(day=1).strftime('%Y-%m-%d')
            if current_year_month == since_date:
                logging.debug("Returning current month category info.")
                db_result = await cls.sub_categories_spent_db_q(current_month=True)
            else:
                logging.debug(f"Returning category info for the month starting: {since_date}.")
                db_result = await cls.sub_categories_spent_db_q(since_date=since_date, specific_month=specific_month)
        else:
            # This will return both the full year, as well as the last X months.
            current_month = await cls.sub_categories_spent_db_q(current_month=True)
            prev_months = await cls.sub_categories_spent_db_q(since_date=since_date, months=months, year=year)

            db_result = []
            # Create a dictionary for fast lookup of values from prev_months
            dict_list = {category['name']: category for category in prev_months}

            # Iterate over list1 and update values with corresponding values from prev_months
            for category in current_month:
                # combined_name = f"{category['category_group_name']} / {category['name']}"
                try:
                    db_result.append({
                        'name': category['name'],
                        'category_group_name': category['category_group_name'],
                        'spent': category['spent'] + dict_list[category['name']]['spent'] \
                            if dict_list[category['name']]['category_group_name'] == category['category_group_name'] else category['spent']
                    })
                except KeyError:
                    if category["spent"] == 0: continue
                    logging.info(f"Subcategory not used in previous months. {category}")
                    db_result.append({
                        'name': category['name'],
                        'category_group_name': category['category_group_name'],
                        'spent': category['spent']
                    })
        
        total_spent = sum(item['spent'] for item in db_result)

        filtered_list = []
        for category in db_result:
            if category["spent"] == 0: continue
            filtered_list.append({
                'name': f"{category['category_group_name']} / {category['name']}",
                'spent': category['spent'],
                'total_spent': total_spent
            })
        
        sorted_list = sorted(filtered_list, key=lambda x: x['spent'])

        return SubCategorySpentResponse(
            since_date=since_date,
            data=sorted_list
        )

    @classmethod # TODO
    async def total_spent(cls, filter_type: Enum, year: Enum = None, months: IntEnum = None, specific_month: Enum = None, \
        transaction_type: Enum = None) -> TotalSpentResponse:
        
        # transactions = await cls.transactions_by_filter_type(
        #     filter_type=filter_type,
        #     year=year,
        #     months=months,
        #     specific_month=specific_month,
        #     transaction_type=transaction_type
        # )
        
        # total_spent = 0.0

        # for account in transactions['data']:
        #     total_spent += account['total']

        # return TotalSpentResponse(
        #     since_date=transactions['since_date'],
        #     total=total_spent
        # )
    
        return None
    
    @classmethod
    async def transactions_by_month_for_year(cls, year: Enum = None) -> TransactionsByMonthResponse:
        since_date = await YnabHelpers.get_date_for_transactions(year=year)
        end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date, year=True)
        
        january = {
            "month_long": "January",
            "month_short": "J",
            "month_year": f"{year.value}-01",
            "total_spent": 0,
            "total_earned": 0
        }
        february = {
            "month_long": "February",
            "month_short": "F",
            "month_year": f"{year.value}-02",
            "total_spent": 0,
            "total_earned": 0
        }
        march = {
            "month_long": "March",
            "month_short": "M",
            "month_year": f"{year.value}-03",
            "total_spent": 0,
            "total_earned": 0
        }
        april = {
            "month_long": "April",
            "month_short": "A",
            "month_year": f"{year.value}-04",
            "total_spent": 0,
            "total_earned": 0
        }
        may = {
            "month_long": "May",
            "month_short": "M",
            "month_year": f"{year.value}-05",
            "total_spent": 0,
            "total_earned": 0
        }
        june = {
            "month_long": "June",
            "month_short": "J",
            "month_year": f"{year.value}-06",
            "total_spent": 0,
            "total_earned": 0
        }
        july = {
            "month_long": "July",
            "month_short": "J",
            "month_year": f"{year.value}-07",
            "total_spent": 0,
            "total_earned": 0
        }
        august = {
            "month_long": "August",
            "month_short": "A",
            "month_year": f"{year.value}-08",
            "total_spent": 0,
            "total_earned": 0
        }
        september = {
            "month_long": "September",
            "month_short": "S",
            "month_year": f"{year.value}-09",
            "total_spent": 0,
            "total_earned": 0
        }
        october = {
            "month_long": "October",
            "month_short": "O",
            "month_year": f"{year.value}-10",
            "total_spent": 0,
            "total_earned": 0
        }
        november = {
            "month_long": "November",
            "month_short": "N",
            "month_year": f"{year.value}-11",
            "total_spent": 0,
            "total_earned": 0
        }
        december = {
            "month_long": "December",
            "month_short": "D",
            "month_year": f"{year.value}-12",
            "total_spent": 0,
            "total_earned": 0
        }

        sorted_months = [january, february, march, april, may, june, july, august, september, october, november, december]

        # From the since date, go through each month and add it to the data
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')

        class TruncMonth(Function):
            database_func = CustomFunction("TO_CHAR", ["column_name", "dt_format"])
        
        db_queryset = YnabTransactions.annotate(
            month_year=TruncMonth('date', 'YYYY-MM'),
            income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('month_year').values('month_year','income','expense').sql()
        logging.debug(f"SQL Query: {db_queryset}")
            
        db_result = await YnabTransactions.annotate(
            month_year=TruncMonth('date', 'YYYY-MM'),
            income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('month_year').values('month_year','income','expense')

        month_match = {
            f'{year.value}-01': january,
            f'{year.value}-02': february,
            f'{year.value}-03': march,
            f'{year.value}-04': april,
            f'{year.value}-05': may,
            f'{year.value}-06': june,
            f'{year.value}-07': july,
            f'{year.value}-08': august,
            f'{year.value}-09': september,
            f'{year.value}-10': october,
            f'{year.value}-11': november,
            f'{year.value}-12': december
        }

        for month in db_result:
            month_match[month['month_year']]['total_spent'] = month['expense']
            month_match[month['month_year']]['total_earned'] = month['income']

        return TransactionsByMonthResponse(
            since_date=since_date,
            data=sorted_months
        )

    @classmethod
    async def transactions_by_months(cls, months: IntEnum = None) -> TransactionsByMonthResponse:
        since_date = await YnabHelpers.get_date_for_transactions(months=months)
        now = localtime()
        # Returns a tuple of year, month. e.g. [(2024, 1), (2023, 12), (2023, 11)]
        months_to_get = [localtime(mktime((now.tm_year, now.tm_mon - n, 1, 0, 0, 0, 0, 0, 0)))[:2] for n in range(months.value)]
        # Swap the results round so that the oldest month is the first index.
        months_to_get.reverse()

        january = {
            "month": 1,
            "month_long": "January",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        february = {
            "month": 2,
            "month_long": "February",
            "month_short": "F",
            "total_spent": 0,
            "total_earned": 0
        }
        march = {
            "month": 3,
            "month_long": "March",
            "month_short": "M",
            "total_spent": 0,
            "total_earned": 0
        }
        april = {
            "month": 4,
            "month_long": "April",
            "month_short": "A",
            "total_spent": 0,
            "total_earned": 0
        }
        may = {
            "month": 5,
            "month_long": "May",
            "month_short": "M",
            "total_spent": 0,
            "total_earned": 0
        }
        june = {
            "month": 6,
            "month_long": "June",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        july = {
            "month": 7,
            "month_long": "July",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        august = {
            "month": 8,
            "month_long": "August",
            "month_short": "A",
            "total_spent": 0,
            "total_earned": 0
        }
        september = {
            "month": 9,
            "month_long": "September",
            "month_short": "S",
            "total_spent": 0,
            "total_earned": 0
        }
        october = {
            "month": 10,
            "month_long": "October",
            "month_short": "O",
            "total_spent": 0,
            "total_earned": 0
        }
        november = {
            "month": 11,
            "month_long": "November",
            "month_short": "N",
            "total_spent": 0,
            "total_earned": 0
        }
        december = {
            "month": 12,
            "month_long": "December",
            "month_short": "D",
            "total_spent": 0,
            "total_earned": 0
        }

        month_list = []
        month_match = {
            '1': january,
            '2': february,
            '3': march,
            '4': april,
            '5': may,
            '6': june,
            '7': july,
            '8': august,
            '9': september,
            '10': october,
            '11': november,
            '12': december
        }

        # add the months in order of oldest, the latest to the result_json
        for index, (year, month) in enumerate(months_to_get):
            add_month = month_match[str(month)]
            add_month['year'] = str(year)
            if month < 10:
                add_month['month_year'] = f"{year}-0{month}"
            else:
                add_month['month_year'] = f"{year}-{month}"
            month_list.insert(index, add_month)

        # From the since date, go through each month and add it to the data
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
        end_date = datetime.now()

        class TruncMonth(Function):
            database_func = CustomFunction("TO_CHAR", ["column_name", "dt_format"])

        db_queryset = YnabTransactions.annotate(
            month_year=TruncMonth('date', 'YYYY-MM'),
            income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('month_year').values('month_year','income','expense').sql()
        logging.debug(f"SQL Query: {db_queryset}")

        db_result = await YnabTransactions.annotate(
            month_year=TruncMonth('date', 'YYYY-MM'),
            income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            expense=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(
                category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES,
                payee_name='BJSS LIMITED',
                join_type='OR'
            )
        ).group_by('month_year').values('month_year','income','expense')

        for month in db_result:
            for filtered_list in month_list:
                if filtered_list['month_year'] == month['month_year']:
                    filtered_list['total_spent'] = month['expense']
                    filtered_list['total_earned'] = month['income']

        return TransactionsByMonthResponse(
            since_date=since_date,
            data=month_list
        )

class YnabHelpers():    
    @classmethod
    async def convert_to_float(cls, amount) -> float:
        # Amount comes in as a milliunit e.g. 21983290
        # It needs to be returned as 21983.29
        return amount / 1000
    
    @classmethod
    async def get_date_for_transactions(cls, year: Enum = None, months: IntEnum = None, specific_month: Enum = None) -> str:
        logging.debug(f'''
        Year: {year}
        Months: {months}
        Specific Month: {specific_month}
        ''')
        if year and not specific_month:
            date_value = datetime.today().replace(year=int(year.value), month=1, day=1).strftime('%Y-%m-%d')
            return date_value
        
        if specific_month and year:
            date_value = datetime.today().replace(year=int(year.value), month=int(specific_month.value), day=1).strftime('%Y-%m-%d')
            return date_value
        
        if specific_month:
            date_value = datetime.today().replace(month=int(specific_month.value), day=1).strftime('%Y-%m-%d')
            return date_value
        
        # If this condition is not set, it'll always return the current month, which would also meet the need for months=1
        if months > 1:
            current_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # When returning months, you need to include the current month. So you therefore need to subtract 1 from the months value.
            month_delta = current_date - relativedelta(months=months - 1)
            return month_delta.strftime('%Y-%m-%d')
    
        return datetime.today().replace(day=1).strftime('%Y-%m-%d')

    @classmethod
    async def get_last_date_from_since_date(cls, since_date: str, year: bool = False) -> datetime:
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
        _, last_day = calendar.monthrange(since_date_dt.year, since_date_dt.month)
        if year:
            return datetime(year=since_date_dt.year, month=12, day=last_day, hour=23, minute=59, second=59)
        return datetime(year=since_date_dt.year, month=since_date_dt.month, day=last_day, hour=23, minute=59, second=59)

    @classmethod
    async def get_route(cls, action: str, param_1: str = None, param_2: str = None, since_date: str = None, month: str = None) -> str:
        '''
        Get the route of the YNAB endpoint you want to call. Passed as a string, returned as a string.
        action = a friendly string of the action needed to be made
        param_1 = budget_id
        param_2 = the section your are calling id (e.g. account_id, or category_id)
        since_date = used for the transactions-list route to get transactions since a specific date. provided in ISO format (e.g. 2016-12-01)
        month = only used when getting categories for a single month. provided in ISO format (e.g. 2016-12-01)

        Source: https://api.ynab.com/v1
        Rate limit: 200 requests per hour
        '''
        match action:
            case 'accounts-list':
                # Returns all accounts
                return f'/budgets/{param_1}/accounts'
            
            case 'accounts-single':
                # Returns a single account
                return f'/budgets/{param_1}/accounts/{param_2}'
            
            case 'budgets-list':
                # Returns budgets list with summary information
                return '/budgets'
            
            case 'budgets-single':
                # Returns a single budget with all related entities. This resource is effectively a full budget export.
                return f'/budgets/{param_1}'
            
            case 'categories-list':
                # Returns all categories grouped by category group. 
                # Amounts (budgeted, activity, balance, etc.) are specific to the current budget month (UTC).
                return f'/budgets/{param_1}/categories'
            
            case 'categories-single':
                # Returns a single category. Amounts (budgeted, activity, balance, etc.) are specific to the current budget month (UTC).
                return f'/budgets/{param_1}/categories/{param_2}'
            
            case 'categories-single-month':
                # Returns a single category for a specific budget month. 
                # Amounts (budgeted, activity, balance, etc.) are specific to the current budget month (UTC).
                # month -> The budget month in ISO format (e.g. 2016-12-01)
                return f'/budgets/{param_1}/months/{month}/categories/{param_2}'
            
            case 'months-list':
                # Returns all budget months
                return f'/budgets/{param_1}/months'
            
            case 'months-single':
                # Returns all budget months
                # month -> The budget month in ISO format (e.g. 2016-12-01)
                return f'/budgets/{param_1}/months/{month}'
            
            case 'payees-list':
                # Returns all payees/merchants
                return f'/budgets/{param_1}/payees'
            
            case 'schedule-transactions-list':
                # Returns all scheduled transactions
                return f'/budgets/{param_1}/scheduled_transactions'
            
            case 'schedule-transactions-single':
                # Returns a single scheduled transaction
                return f'/budgets/{param_1}/scheduled_transactions/{param_2}'
            
            case 'transactions-list':
                # Returns budget transactions
                if param_2: return f'/budgets/{param_1}/transactions?server_knowledge={param_2}'
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/transactions'
                return f'/budgets/{param_1}/transactions?since_date={since_date}'
            
            case 'transactions-single':
                # Returns a single transaction
                return f'/budgets/{param_1}/transactions/{param_2}'
            
            case 'transactions-list-account':
                # Returns all transactions for a specified account
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/accounts/{param_2}/transactions'
                return f'/budgets/{param_1}/accounts/{param_2}/transactions?since_date={since_date}'
            
            case 'transactions-list-category':
                # Returns all transactions for a specified category
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/categories/{param_2}/transactions'
                return f'/budgets/{param_1}/categories/{param_2}/transactions?since_date={since_date}'
            
            case 'transactions-list-payee':
                # Returns all transactions for a specified payee
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/payees/{param_2}/transactions'
                return f'/budgets/{param_1}/payees/{param_2}/transactions?since_date={since_date}'
            
            case _:
                return '/user'

    @classmethod
    async def get_pydantic_model(cls, action: str) -> Model | HTTPException:
        model_list = {
            "accounts-list": Account,
            "categories-list": Category,
            "months-list": MonthSummary,
            "months-single": MonthDetail,
            "payees-list": Payee,
            "transactions-list": TransactionDetail
        }

        try:
            logging.debug(f"Attempting to get pydantic model for {action}")
            return model_list[action]
        except KeyError:
            logging.warning(f"Pydantic model for {action} doesn't exist.")
            raise HTTPException(status_code=400)

    @classmethod
    @alru_cache(maxsize=32) # Caches requests so we don't overuse them.
    async def make_request(cls,
            action: str,
            param_1: str = None,
            param_2: str = None,
            since_date: str = None,
            month: str = None,
            year: Enum = None,
            skip_sk: bool = False
        ) -> dict | HTTPException:
        '''
        Check if the route exists in server knowledge
            If it does, check the entities are up to date
                If they are return the DB entities
            If they're not, make the api call
        Once the API call is made, save them to the DB
            Then return the DB entities
        '''
        ynab_route = await cls.get_route(action, param_1, param_2, since_date, month)
        ynab_url = dotenv_ynab_url + ynab_route

        # For debugging purposes only.
        # skip_sk = True
        server_knowledge = None
        # TODO split this out to a separate function
        try:
            sk_eligible = await YnabServerKnowledgeHelper.check_route_eligibility(action)
            sk_route = await cls.get_route(action, param_1)
            server_knowledge = await YnabServerKnowledgeHelper.check_if_exists(route_url=sk_route)
            if sk_eligible and not skip_sk:
                logging.debug("Route is eligible, checking if there are any saved DB entities.")
                if server_knowledge:
                    logging.info("Route already exists in DB, checking if its up to date.")
                    is_up_to_date = await YnabServerKnowledgeHelper.current_date_check(server_knowledge.last_updated)
                    if is_up_to_date:
                        logging.info("Date is the same as today, returning the DB entities.")
                        return await cls.return_db_model_entities(action=action, since_date=since_date, month=month, year=year)
                    logging.debug(f"Updating ynab url to include server_knowledge value: {ynab_url}")
                    ynab_url = await YnabServerKnowledgeHelper.add_server_knowledge_to_url(
                        ynab_url=ynab_url,
                        server_knowledge=server_knowledge.server_knowledge
                    )
            else:
                logging.debug("Route is not eligible.")
            if skip_sk:
                logging.info("Skipping returning the DB entities. Making API call.")
        except Exception as exc:
            logging.exception("Continuing to just call the API instead.", exc_info=exc)
            pass

        # TODO split this out to a separate function
        logging.debug(f'Date is not the same as today or there was an issue getting the DB entities, attempting to call YNAB with {ynab_url}')
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(ynab_url, headers={'Authorization': f"Bearer {dotenv_ynab_token}"})
            except httpx.HTTPError as exc:
                logging.exception(exc)
                raise HTTPException(status_code=500)
            finally:
                # TODO split this out to a separate function
                if sk_eligible:
                    logging.debug("Updating/creating new entities")
                    action_data_name = await YnabServerKnowledgeHelper.get_route_data_name(action)
                    resp_entity_list = response.json()["data"][action_data_name]
                    await YnabServerKnowledgeHelper.process_entities(action=action, entities=resp_entity_list)
                    resp_server_knowledge = response.json()["data"]["server_knowledge"]
                    await YnabServerKnowledgeHelper.create_update_server_knowledge(
                        route=sk_route,
                        server_knowledge=resp_server_knowledge,
                        db_entity=server_knowledge
                    )
                    logging.debug("Server knowledge created/updated.")
                    return await cls.return_db_model_entities(action=action, since_date=since_date, month=month, year=year)
                logging.info("Route is not sk eligible, returning the JSON response.")
                return await cls.return_pydantic_model_entities(json_response=response.json(), action=action)

    @classmethod
    async def pydantic_accounts(cls) -> list[YnabAccounts]:
        return await cls.make_request('accounts-list', param_1=dotenv_ynab_budget_id)
    
    @classmethod
    async def pydantic_categories(cls) -> list[YnabCategories]:
        return await cls.make_request('categories-list', param_1=dotenv_ynab_budget_id)
    
    @classmethod
    async def pydantic_month_details(cls) -> list[YnabMonthSummaries]: # TODO cron this once a month
        current_month = datetime.today().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_month = current_month - relativedelta(months=1)
        prev_month_string = previous_month.strftime('%Y-%m-%d')
        # Check if the previous month categories exist in the DB
        logging.debug(f"Checking if any previous month categories exist for {prev_month_string}")
        prev_month_entities = await YnabMonthDetailCategories.filter(month_summary_fk__month=previous_month).all()
        # If its already been stored, skip it otherwise make the API call.
        if len(prev_month_entities) > 0: return { "message": "Already stored for the previous month" }
        # Get the month summary
        month_summary_entity = await YnabMonthSummaries.filter(month=previous_month).get_or_none()
        if month_summary_entity is None: return {"message": "no month summary available. run update_month_summaries."}
        # Get the entities to store
        json_month_list = await cls.make_request('months-single', param_1=dotenv_ynab_budget_id, month=prev_month_string)
        # Then store the entities in the DB.
        for category in json_month_list:
            category["month_summary_fk"] = month_summary_entity

        await YnabServerKnowledgeHelper.process_entities(action='months-single', entities=json_month_list)
        return { "message": "Complete" }

    @classmethod
    async def pydantic_month_summaries(cls) -> list[YnabMonthSummaries]:
        return await cls.make_request('months-list', param_1=dotenv_ynab_budget_id)

    @classmethod
    async def pydantic_payees(cls) -> list[YnabPayees]:
        return await cls.make_request('payees-list', param_1=dotenv_ynab_budget_id)
    
    @classmethod
    async def pydantic_transactions(cls, since_date: str = None, month: str = None, year: Enum = None, skip_sk: bool = None) -> list[YnabTransactions]:
        return await cls.make_request('transactions-list', param_1=dotenv_ynab_budget_id, since_date=since_date, month=month, year=year, skip_sk=skip_sk)

    @classmethod
    async def return_db_model_entities(cls, action: str, since_date: str = None, month: Enum = None, year: Enum = None) -> list[Model]:
        logging.info("Returning DB entities.")
        db_model = await YnabServerKnowledgeHelper.get_sk_model(action=action)
        if since_date and not (year and month):
            todays_date = datetime.today().strftime('%Y-%m-%d')
            logging.debug(f"Returning DB entities from {since_date} to {todays_date}")
            queryset = db_model.filter(date__range=(since_date, todays_date)).order_by('-date') # DESC
        elif month and year:
            # Convert since_date to datetime
            since_date = datetime(int(year.value), int(month.value), 1)
            # Find the first day of the next month
            first_day_of_next_month = since_date + timedelta(days=32)
            # Calculate the last day of the current month
            last_day_of_month = first_day_of_next_month.replace(day=1) - timedelta(days=1)
            to_date = last_day_of_month.strftime('%Y-%m-%d')
            # Set the from date to the last day of that month.
            logging.debug(f"Returning transactions for the entire month of {since_date.strftime('%Y-%m-%d')} - {to_date}")
            queryset = db_model.filter(date__range=(since_date, to_date)).order_by('-date') # DESC
        else:
            logging.debug("Returning all entities.")
            if action == 'transactions-list':
                queryset = db_model.all().order_by('-date')
            else:
                queryset = db_model.all()

        # Make the DB call, and return them as dicts
        db_entities = await queryset.values()

        # Return the entities as if they were pydantic models from ynab.
        db_pydantic_model = await cls.get_pydantic_model(action=action)
        return TypeAdapter(list[db_pydantic_model]).validate_python(db_entities)

    @classmethod
    async def return_pydantic_model_entities(cls, json_response: json, action: str) -> list[Model]:
        match action:
            case 'accounts-list':
                pydantic_accounts_list = AccountsResponse.model_validate_json(json.dumps(json_response))
                return pydantic_accounts_list.data.accounts
            case 'categories-list':
                pydantic_categories_list = CategoriesResponse.model_validate_json(json.dumps(json_response))
                return pydantic_categories_list.data.category_groups
            case 'months-single':
                return json_response["data"]["month"]["categories"]
            case 'months-list':
                pydantic_months_list = MonthSummariesResponse.model_validate_json(json.dumps(json_response))
                return pydantic_months_list.data.months
            case 'payees-list':
                pydantic_payees_list = PayeesResponse.model_validate_json(json.dumps(json_response))
                return pydantic_payees_list.data.payees
            case 'transactions-list':
                pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(json_response))
                return pydantic_transactions_list.data.transactions
            case _:
                logging.exception(f"Tried to return an endpoint we don't support yet. {action}")
                raise HTTPException(status_code=500)

    @classmethod
    async def sync_transaction_rels(cls):
        # Get all the transactions that don't have a category_fk set
        transactions_no_cat_fk = await YnabTransactions.filter(category_fk=None)
        transactions_to_update = await YnabTransactions.filter(category_fk=None).count()

        if transactions_to_update < 1: return {"message": "All transactions have category fk's synced."}

        skipped_transactions = 0
        # Go through each transaction that doesn't have a category_fk set
        for transaction in transactions_no_cat_fk:
            # Search on the ynabcategories table for the ID
            category_entity = await YnabCategories.filter(id=transaction.category_id).get_or_none()

            if category_entity is None:
                if transaction.transfer_account_id is not None:
                    logging.info(f"Transaction is a transfer, ignoring: {transaction.id}")    
                else:
                    logging.warn(f"Category may not be set for transaction: {transaction.id}")
                skipped_transactions += 1
                continue
            
            # Set the category_fk
            logging.debug(f"Assigning Category Group: {category_entity.category_group_name} to {transaction.id}")
            transaction.category_fk = category_entity
            await transaction.save()

        logging.info(f'''
        Total to sync: {transactions_to_update}
        Total skipped: {skipped_transactions}
        Total synced: {transactions_to_update-skipped_transactions}
        ''')
        return {"message": "Complete."}

class YnabServerKnowledgeHelper():
    @classmethod
    async def add_server_knowledge_to_url(cls, ynab_url: str, server_knowledge: int) -> bool:
        # If a ? exists in the URL then append the additional param.
        if '?' in ynab_url:
            return f"{ynab_url}&server_knowledge={server_knowledge}"
            
        # Otherwise add a ? and include the sk param.
        return f"{ynab_url}?server_knowledge={server_knowledge}"

    @classmethod
    async def check_if_exists(cls, route_url: str) -> YnabServerKnowledge | None:
        return await YnabServerKnowledge.get_or_none(route=route_url)

    @classmethod
    async def check_route_eligibility(cls, action: str) -> bool:
        capable_routes = ['accounts-list','categories-list','months-list','payees-list','transactions-list']
        return action in capable_routes

    @classmethod
    async def create_update_route_entities(cls, resp_body: dict, model: Model) -> int:
        try:
            obj = await model.create(**resp_body)
            logging.debug(f"New entity created {obj.id}")
            return 1
        except IntegrityError:
            entity_id = resp_body["id"]
            resp_body.pop("id")
            obj = await model.filter(id=entity_id).update(**resp_body)
            logging.debug(f"Entity updated")
            return 0
        except FieldError as e_field:
            logging.exception("Issue with a field value", exc_info=e_field)
            return 0
        except Exception as exc:
            logging.exception("Issue create/update entity.", exc_info=exc)
            return 0

    @classmethod
    async def create_update_server_knowledge(cls, route: str, server_knowledge: int,
        db_entity: YnabServerKnowledge = None) -> YnabServerKnowledge:
        try:
            if db_entity:
                logging.debug(f"Updating server knowledge for {route} to {server_knowledge}")
                db_entity.last_updated = datetime.today()
                db_entity.server_knowledge = server_knowledge
                await db_entity.save()
                return db_entity
            logging.debug(f"Creating server knowledge for {route} to {server_knowledge}")
            return await YnabServerKnowledge.create(
                budget_id=dotenv_ynab_budget_id,
                route=route,
                last_updated=datetime.today(),
                server_knowledge=server_knowledge
            )
        except Exception as exc:
            logging.exception("Issue create/update server knowledge.", exc_info=exc)
            raise HTTPException(status_code=500)
    
    @classmethod
    async def current_date_check(cls, date_to_check: datetime) -> bool:
        current_date = datetime.today().strftime('%Y-%m-%d')
        date_to_check = date_to_check.strftime('%Y-%m-%d')
        logging.debug(f"Checking if {current_date} is the same as {date_to_check}")
        return current_date == date_to_check
    
    @classmethod
    async def get_route_data_name(cls, action: str) -> str | HTTPException:
        data_name_list = {
            "accounts-list": "accounts",
            "categories-list": "category_groups",
            "months-list": "months",
            "payees-list": "payees",
            "transactions-list": "transactions"
        }

        try:
            logging.debug(f"Attempting to get a data name for {action}")
            return data_name_list[action]
        except KeyError:
            logging.warning(f"Data name for {action} doesn't exist.")
            raise HTTPException(status_code=400)

    @classmethod
    async def get_sk_model(cls, action: str) -> Model | HTTPException:
        model_list = {
            "accounts-list": YnabAccounts,
            "categories-list": YnabCategories,
            "months-single": YnabMonthDetailCategories,
            "months-list": YnabMonthSummaries,
            "payees-list": YnabPayees,
            "transactions-list": YnabTransactions
        }

        try:
            logging.debug(f"Attempting to get a model for {action}")
            return model_list[action]
        except KeyError:
            logging.warning(f"Model for {action} doesn't exist.")
            raise HTTPException(status_code=400)
    
    @classmethod
    async def process_entities(cls, action: str, entities: dict) -> dict:
        model = await cls.get_sk_model(action)

        if action == 'categories-list':
            # Need to loop on each of the category groups as they are not presented as one full list.
            entity_list = []
            for group in entities:
                for category in group["categories"]:
                    entity_list.append(category)
            logging.debug(f"List of categories {entity_list}.")
        else:
            entity_list = entities

        created = 0
        for entity in entity_list:
            logging.debug(entity)
            if action == 'transactions-list': entity.pop('subtransactions')
            obj = await cls.create_update_route_entities(resp_body=entity, model=model)
            created += obj
        
        logging.debug(f"Created {created} entities. Updated {len(entities) - created} entities")
        return { "message": "Complete" }
