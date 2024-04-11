import logging
import calendar
from enum import Enum, IntEnum
from time import localtime, mktime
from datetime import datetime
from dateutil.relativedelta import relativedelta
from fastapi import HTTPException
from itertools import groupby
from tortoise.functions import Sum
from tortoise.expressions import RawSQL, Q, Function
from pypika import CustomFunction
from app.ynab.helpers import YnabHelpers
from app.db.models import YnabAccounts, YnabCategories, YnabMonthDetailCategories, YnabTransactions, Budgets
from app.enums import TransactionTypeOptions, FilterTypes, PeriodOptions # TODO ensure enums are used in all functions
from app.ynab.schemas import AvailableBalanceResponse, CardBalancesResponse, CategorySpentResponse, CategorySpent, \
    CreditAccountResponse, EarnedVsSpentResponse, IncomeVsExpensesResponse, LastXTransactions, SpentInPeriodResponse, \
    SpentVsBudgetResponse, SubCategorySpentResponse, TotalSpentResponse, TransactionsByMonthResponse, Month, TransactionSummary

# TODO ensure transactions are returned as non-negative values (e.g. ynab returns as -190222, alter to ensure its stored as 190222)
# TODO learn how to use decorators in Python (e.g. if im logging all the sql and then running the query, can probably do that via a decorator)
# Could also use decorators for processing params

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
    async def card_balances(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> CardBalancesResponse:
        db_queryset = YnabAccounts.filter(
            type__not='checking'
        ).values('name','balance',cleared='cleared_balance',uncleared='uncleared_balance')
        
        db_result = await db_queryset

        logging.debug(f"DB Query: {db_queryset.sql()}")
        logging.debug(f"DB Result: {db_result}")

        # TODO support date filtering

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
                'income': sum(entry['income'] for entry in entries),
                'expenses': sum(entry['expense'] for entry in entries)
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

        # Limit is set to 3 in hopes that it would always return the last paid dates for each account
        db_queryset = YnabTransactions.filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(transfer_account_id__isnull=False),
            Q(account_name__not_in=["HSBC ADVANCE"])
        ).group_by('account_name', 'id').order_by('-date').limit(3).values('id','date','amount','account_name').sql()
        logging.debug(f"SQL Query: {db_queryset}")

        db_results = await YnabTransactions.filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(transfer_account_id__isnull=False),
            Q(account_name__not_in=["HSBC ADVANCE"])
        ).group_by('account_name', 'id').order_by('-date').limit(3).values('id','date','amount','account_name')

        return CreditAccountResponse(
            since_date=since_date,
            data=db_results
        )

    @classmethod
    async def last_x_transactions(cls, count: int, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> LastXTransactions:
        since_date = await YnabHelpers.get_date_for_transactions(year=year, months=months, specific_month=specific_month)
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
        
        # For year and specific month - get the last date of that month and then the last x transactions
        if year and specific_month:
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date)
        else:
            end_date = datetime.now()

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
    async def count_in_category(cls, category: Enum, subcategory: Enum, months: IntEnum = None, year: Enum = None, specific_month: Enum = None):
        # e.g. how many transactions exist for category x, and subcat y.
        # or just one or the other
        return

    @classmethod
    async def month_summary(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> Month:
        if not months and not year and not specific_month:
            # Filters for income and bills for the entire of last month.
            last_month_end = datetime.now().replace(day=1, hour=23, minute=59, second=59, microsecond=59) - relativedelta(days=1)
            last_month_start = last_month_end.replace(day=1, hour=00, minute=00, second=00, microsecond=00)
        else:
            # TODO finish this
            # if not current month use the previous month summaries to work it out
            logging.debug("not current month")
            last_month_end = datetime.now().replace(day=1, hour=23, minute=59, second=59, microsecond=59) - relativedelta(days=1)
            last_month_start = last_month_end.replace(day=1, hour=00, minute=00, second=00, microsecond=00)
        
        db_query = await YnabTransactions.annotate(
            income=Sum(RawSQL('CASE WHEN "amount" >= 0 THEN "amount" ELSE 0 END')),
            bills=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(
                category_fk__category_group_name__in=['Monthly Bills', 'Loans'],
                payee_name='BJSS LIMITED',
                join_type='OR'
            ),
            Q(date__gte=last_month_start),
            Q(date__lt=last_month_end)
        ).group_by('cleared').first().values('income', 'bills')

        income = db_query.get('income')
        bills = db_query.get('bills')
        logging.debug(f"Income: {income}. Bills: {bills}")

        # update the from date to the beginning of the month for everything spent so far.
        this_month_start = last_month_start + relativedelta(months=1)
        this_month_end = last_month_end + relativedelta(months=1)

        categories = await YnabTransactions.annotate(
            spent=Sum(RawSQL('"ynabtransactions"."amount"'))
        ).filter(
            category_fk__category_group_name__not_in=['Monthly Bills', 'Loans'],
            date__gte=this_month_start,
            date__lt=this_month_end,
            transfer_account_id__isnull=True
        ).group_by(
            'category_fk__category_group_name','category_name','category_fk__budget__amount'
        ).all().values('spent',name='category_name',group='category_fk__category_group_name',budget='category_fk__budget__amount')
        # ex output: 
        # [{'name': 'Coffee', 'group': 'Frequent', 'spent': -9950.0, 'budget': 50},
        # {'name': 'Restaurants', 'group': 'Frequent', 'spent': -6000.0, 'budget': 50}]
        
        categories = sorted(categories, key=lambda x: x['spent'], reverse=False)

        balance_spent = 0
        balance_budget = 0

        for category in categories:
            if category['budget'] is None:
                category['budget'] = 0
            balance_spent += category.get('spent')
            balance_budget +=  category.get('budget')

        logging.debug(f"Total spent this month: {balance_spent}")
        logging.debug(f"Total budgeted: {balance_budget}")

        balance_available = income - (balance_spent - bills)

        days_left = await YnabHelpers.get_days_left_from_current_month()
        daily_spend = (income - (balance_spent - bills)) / days_left

        uncategorised_transactions = await YnabTransactions.filter(category_fk_id=None, transfer_account_id=None).count()

        notification_text = f"{uncategorised_transactions} uncategorised transactions" \
            if uncategorised_transactions > 1 else "1 uncategorised transaction" if uncategorised_transactions > 0 else None

        return Month(
            notif=notification_text,
            summary={
                'days_left': days_left,
                'balance_available': balance_available,
                'balance_spent': balance_spent,
                'balance_budget': balance_budget,
                'daily_spend': daily_spend
            },
            categories=categories[0:3],
            income_expenses={
                'income': income,
                'bills': bills,
                'balance_spent': balance_spent,
                'balance_available': balance_available
            }
        )

    @classmethod
    async def spent_in_period(cls, period: Enum) -> SpentInPeriodResponse:
        # Set the defaults to today.
        since_date = datetime.today().replace(hour=00, minute=00, second=00, microsecond=00)
        end_date = datetime.today().replace(hour=23, minute=59, second=59, microsecond=59)

        match period.value:
            case 'YESTERDAY':
                since_date = since_date - relativedelta(days=1)
                end_date = end_date - relativedelta(days=1)
            case 'THIS_WEEK': # Weeks run from Monday to Sunday
                # Minus the start_date by the current weekday. This sets it to Monday within that week.
                since_date = since_date - relativedelta(days=since_date.weekday())
                end_of_week = since_date + relativedelta(days=6)
                end_date = end_of_week.replace(hour=23, minute=59, second=59, microsecond=59)
            case 'LAST_WEEK':
                start_of_week = since_date - relativedelta(days=since_date.weekday())
                since_date = start_of_week - relativedelta(weeks=1)
                end_of_week = since_date + relativedelta(days=6)
                end_date = end_of_week.replace(hour=23, minute=59, second=59, microsecond=59)
            case _: # 'TODAY' is the default
                pass
        
        db_queryset = YnabTransactions.annotate(
            spent=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date),
            Q(date__lte=end_date),
            Q(category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES)
        ).group_by('deleted').values('spent').sql()
        logging.debug(f"SQL Query: {db_queryset}")
        
        db_results = await YnabTransactions.annotate(
            spent=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date),
            Q(date__lte=end_date),
            Q(category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES)
        ).group_by('deleted').values('spent')

        try: #TODO move this to a separate function to share across all DB queries
            spent_amount = db_results[0]['spent']
        except IndexError:
            spent_amount = 0

        return SpentInPeriodResponse(
            period=period.value,
            spent=spent_amount
        )

    @classmethod
    async def spent_vs_budget(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> SpentVsBudgetResponse:
        spent_categories = await cls.categories_spent(months=months, year=year, specific_month=specific_month)
        
        total_budgeted = 0.0 # Budget assigned to the category
        total_spent = 0.0
        for category in spent_categories.data:
            total_spent += category.spent
            total_budgeted += category.budget
            logging.debug(f'''
            Category details:
                name: {category.name}
                spent: {category.spent}
                budgeted: {category.budget}
            ''')

        logging.debug(f'''
        Total Spent: {total_spent}
        Total Budgeted: {total_budgeted}
        ''')

        return SpentVsBudgetResponse(
            balance=total_budgeted - total_spent,
            budget=total_budgeted,
            spent=total_spent
        )

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

    @classmethod
    async def total_spent(cls, year: Enum = None, months: IntEnum = None, specific_month: Enum = None) -> TotalSpentResponse:
        since_date = await YnabHelpers.get_date_for_transactions(year=year, months=months, specific_month=specific_month)
        if months:
            end_date = datetime.now()
        elif year and specific_month:
            # Set the date to the last day of the current month.
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date)
        elif year:
            # Set the date to the last day of the current year.
            end_date = await YnabHelpers.get_last_date_from_since_date(since_date=since_date, year=True)
        
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')

        db_queryset = YnabTransactions.annotate(
            spent=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES)
        ).group_by('deleted').values('spent').sql()
        logging.debug(f"SQL Query: {db_queryset}")

        db_results = await YnabTransactions.annotate(
            spent=Sum(RawSQL('CASE WHEN "amount" < 0 THEN "amount" ELSE 0 END'))
        ).filter(
            Q(date__gte=since_date_dt),
            Q(date__lte=end_date),
            Q(category_fk__category_group_name__in=YNAB.CAT_EXPENSE_NAMES)
        ).group_by('deleted').values('spent')
    
        return TotalSpentResponse(
            since_date=since_date,
            total_spent=db_results[0]['spent']
        )
    
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

    @classmethod
    async def transaction_summary(cls, months: IntEnum = None, year: Enum = None, specific_month: Enum = None) -> TransactionSummary:
        if not months and not year and not specific_month:
            accounts = await YnabAccounts.filter(type='creditCard')\
                .values('name', 'balance', cleared='cleared_balance', uncleared='uncleared_balance')
            total_balance = sum(account['balance'] for account in accounts)
            # Filters for transactions for the entire of last month.
            month_end = datetime.now().replace(day=1, hour=23, minute=59, second=59, microsecond=59) - relativedelta(days=1) + relativedelta(months=1)
            month_start = month_end.replace(day=1, hour=00, minute=00, second=00, microsecond=00)
        else:
            # TODO finish this
            accounts = await YnabAccounts.filter(type='creditCard')\
                .values('name', 'balance', cleared='cleared_balance', uncleared='uncleared_balance')
            total_balance = sum(account['balance'] for account in accounts)
            month_end = datetime.now().replace(day=1, hour=23, minute=59, second=59, microsecond=59) - relativedelta(days=1) + relativedelta(months=1)
            month_start = month_end.replace(day=1, hour=00, minute=00, second=00, microsecond=00)
        
        transactions = await YnabTransactions.filter(
            category_fk__category_group_name__not_in=['Monthly Bills', 'Loans'],
            date__gte=month_start,
            date__lt=month_end,
            transfer_account_id__isnull=True
        ).order_by('-date').all().values('amount','date',category='category_fk__category_group_name',subcategory='category_name',payee='payee_name')

        return TransactionSummary(
            summary={
                'total':total_balance,
                'accounts': accounts
            },
            transactions=transactions
        )