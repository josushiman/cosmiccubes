import logging
from enum import Enum, IntEnum
from tortoise.queryset import QuerySet
from tortoise.functions import Sum
from tortoise.expressions import RawSQL, Q, Function
from app.ynab.schemas import AvailableBalanceResponse, CardBalancesResponse, CategorySpentResponse, CategorySpent, \
    CreditAccountResponse, EarnedVsSpentResponse, IncomeVsExpensesResponse, LastXTransactions, SpentInPeriodResponse, \
    SpentVsBudgetResponse, SubCategorySpentResponse, TotalSpentResponse, TransactionsByMonthResponse
from app.db.models import YnabAccounts, YnabCategories, YnabMonthDetailCategories, YnabTransactions
from app.ynab.main import YNAB
from app.decorators import log_sql_query

class YnabDBQueries(): #TODO
    @classmethod
    async def log_query(cls, db_queryset: QuerySet) -> None:
        logging.debug(f"DB Query: {db_queryset.sql()}")
        # Maybe return the result instead of just logging the query?
        # Could be an issue for queries which need can't just be called on the QuerySet.
        return
    
    @classmethod
    async def available_balance(cls):
        db_queryset = YnabAccounts.annotate(
            available=Sum('balance'),
            spent=Sum(RawSQL('''CASE WHEN "type" != 'checking' THEN "balance" ELSE 0 END''')),
            total=Sum(RawSQL('''CASE WHEN "type" = 'checking' THEN "balance" ELSE 0 END'''))
        ).first().values('total','spent','available')
        
        db_result = await db_queryset

        await cls.log_query(db_queryset=db_queryset)
        logging.debug(f"DB Result: {db_result}")

        return db_result

    @classmethod
    async def categories_spent(cls,
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
