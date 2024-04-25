import logging
from enum import Enum, IntEnum
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from tortoise.functions import Sum
from tortoise.expressions import Q
from app.ynab.helpers import YnabHelpers
from app.enums import (
    LoansAndRenewalsEnum,
    PeriodMonthOptionsIntEnum,
    SpecificMonthOptionsEnum,
    SpecificYearOptionsEnum,
)
from app.db.models import (
    YnabAccounts,
    YnabCategories,
    YnabTransactions,
    Budgets,
    Savings,
    LoansAndRenewals,
)
from app.ynab.schemas import (
    Month,
    TransactionSummary,
    CategorySummary,
    SubCategorySummary,
    BudgetsNeeded,
    UpcomingBills,
    CategoryTransactions,
    UpcomingBillsDetails,
    LoanPortfolio,
    DirectDebitSummary,
    Insurance,
    Refunds,
)


class YNAB:
    CAT_EXPENSE_NAMES = ["Frequent", "Giving", "Non-Monthly Expenses", "Work"]
    EXCLUDE_EXPENSE_NAMES = ["Monthly Bills", "Loans", "Credit Card Payments"]

    @classmethod
    async def budgets_needed(cls) -> BudgetsNeeded:
        subcategories_count = await YnabCategories.filter(
            category_group_name__not_in=[
                *cls.EXCLUDE_EXPENSE_NAMES,
                "Internal Master Category",
                "Yearly Bills",
                "Non-Monthly Expenses",
            ],
            budget__isnull=True,
        ).count()

        subcategories = (
            await YnabCategories.filter(
                category_group_name__not_in=[
                    *cls.EXCLUDE_EXPENSE_NAMES,
                    "Internal Master Category",
                    "Yearly Bills",
                    "Non-Monthly Expenses",
                ],
                budget__isnull=True,
            )
            .order_by("category_group_name", "name")
            .all()
            .values("name", category="category_group_name")
        )

        return BudgetsNeeded(count=subcategories_count, subcategories=subcategories)

    @classmethod
    async def categories_summary(
        cls,
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ) -> list[CategorySummary]:
        if not months and not year and not specific_month:
            # Filters for income and bills for the entire of last month.
            month_end = (
                datetime.now().replace(
                    day=1, hour=23, minute=59, second=59, microsecond=59
                )
                - relativedelta(days=1)
                + relativedelta(months=1)
            )
            month_start = month_end.replace(
                day=1, hour=00, minute=00, second=00, microsecond=00
            )
        else:
            # TODO finish this
            # if not current month use the previous month summaries to work it out
            month_end = (
                datetime.now().replace(
                    day=1, hour=23, minute=59, second=59, microsecond=59
                )
                - relativedelta(days=1)
                + relativedelta(months=1)
            )
            month_start = month_end.replace(
                day=1, hour=00, minute=00, second=00, microsecond=00
            )

        categories = (
            await YnabCategories.annotate(spent=Sum("activity"))
            .filter(category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES, spent__gt=0)
            .group_by("id", "category_group_id", "category_group_name", "name")
            .order_by("-spent")
            .values(
                "spent",
                id="category_group_id",
                name="category_group_name",
                subcategory="name",
                subcategory_id="id",
            )
        )

        budget_entities = await Budgets.all()
        budgets = {budget.category_id: budget.amount for budget in budget_entities}

        grouped_data = {}
        for category in categories:
            category_id = category["id"]
            category_name = category["name"]
            subcategory = category["subcategory"]
            subcategory_id = category["subcategory_id"]
            amount = category["spent"]
            if category_name not in grouped_data:
                grouped_data[category_name] = {
                    "id": category_id,
                    "amount": 0,
                    "budgeted": 0,
                    "subcategories": [],
                }
            grouped_data[category_name]["amount"] += amount
            try:
                grouped_data[category_name]["budgeted"] += budgets[subcategory_id]
                grouped_data[category_name]["subcategories"].append(
                    {
                        "name": subcategory,
                        "amount": amount,
                        "budgeted": budgets[subcategory_id],
                    }
                )
            except KeyError:
                grouped_data[category_name]["budgeted"] += 0
                grouped_data[category_name]["subcategories"].append(
                    {"name": subcategory, "amount": amount, "budgeted": 0}
                )

        category_summaries = []
        for category, summary in grouped_data.items():
            category_summary = CategorySummary(
                id=summary["id"],
                category=category,
                amount=summary["amount"],
                budgeted=summary["budgeted"],
                status=(
                    "on track"
                    if summary["budgeted"] >= summary["amount"]
                    else "overspend"
                ),
                subcategories=[
                    SubCategorySummary(**subcat) for subcat in summary["subcategories"]
                ],
            )
            category_summaries.append(category_summary)

        return category_summaries

    @classmethod
    async def category_summary(
        cls, category_name: str, subcategory_name: str
    ) -> CategoryTransactions:
        month_end = (
            datetime.now().replace(day=1, hour=23, minute=59, second=59, microsecond=59)
            - relativedelta(days=1)
            + relativedelta(months=1)
        )
        month_start = month_end.replace(
            day=1, hour=00, minute=00, second=00, microsecond=00
        )

        subcategory_name = subcategory_name.replace("-", " ")

        category = (
            await YnabCategories.filter(
                category_group_name__iexact=category_name,
                name__iexact=subcategory_name,
            )
            .first()
            .values("activity")
        )

        category_spent = category.get("activity")

        transactions = (
            await YnabTransactions.filter(
                category_fk__category_group_name__iexact=category_name,
                category_name__iexact=subcategory_name,
                date__gte=month_start,
                date__lt=month_end,
                debit=True,
            )
            .order_by("-date")
            .all()
            .values(
                "id",
                "account_id",
                "amount",
                "date",
                category="category_fk__category_group_name",
                subcategory="category_name",
                payee="payee_name",
            )
        )

        last_month_start = month_start - relativedelta(months=1)
        last_3_month_start = month_start - relativedelta(months=3)
        last_6_month_start = month_start - relativedelta(months=6)
        last_month_end = month_end - relativedelta(months=1)

        transactions_1_m = (
            await YnabTransactions.annotate(spent=Sum("amount"))
            .filter(
                category_fk__category_group_name__iexact=category_name,
                category_name__iexact=subcategory_name,
                date__gte=last_month_start,
                date__lt=last_month_end,
                debit=True,
            )
            .group_by("deleted")
            .get_or_none()
            .values("spent")
        )
        if not transactions_1_m:
            transactions_1_m = {"spent": 0}

        transactions_3_m = (
            await YnabTransactions.annotate(spent=Sum("amount"))
            .filter(
                category_fk__category_group_name__iexact=category_name,
                category_name__iexact=subcategory_name,
                date__gte=last_3_month_start,
                date__lt=last_month_end,
                debit=True,
            )
            .group_by("deleted")
            .get_or_none()
            .values("spent")
        )
        if not transactions_3_m:
            transactions_3_m = {"spent": 0}

        transactions_6_m = (
            await YnabTransactions.annotate(spent=Sum("amount"))
            .filter(
                category_fk__category_group_name__iexact=category_name,
                category_name__iexact=subcategory_name,
                date__gte=last_6_month_start,
                date__lt=last_month_end,
                debit=True,
            )
            .group_by("deleted")
            .get_or_none()
            .values("spent")
        )
        if not transactions_6_m:
            transactions_6_m = {"spent": 0}

        transactions_1_m["period"] = 1
        transactions_3_m["period"] = 3
        transactions_6_m["period"] = 6
        logging.debug(f"Current monthly spend for category: {category_spent}")
        transaction_totals = [transactions_1_m, transactions_3_m, transactions_6_m]
        trends = []
        for totals in transaction_totals:
            average_spend = totals["spent"] / totals["period"]
            logging.debug(f"Average spend for last {totals['period']}: {average_spend}")

            # TODO maybe swap this out for the current calc?
            # try:
            #     trend_perc = (
            #         (category_spent - totals["spent"]) / totals["spent"]
            #     ) * 100
            #     logging.error(f"Test trend percentage: {trend_perc}")
            # except ZeroDivisionError:
            #     pass

            if average_spend > 0:
                trend_percentage = round((category_spent / average_spend) * 100)
            else:
                trend_percentage = 0
            logging.debug(f"Trend percentage: {trend_percentage}")

            trend_string = (
                "up"
                if trend_percentage > 0
                else "down" if trend_percentage < 0 else "flat"
            )
            period_string = (
                f"L{totals['period']} months" if totals["period"] > 1 else "Last month"
            )

            trends.append(
                {
                    "avg_spend": average_spend,
                    "period": period_string,
                    "trend": trend_string,
                    "percentage": trend_percentage,
                }
            )

        return CategoryTransactions(
            total=category_spent, trends=trends, transactions=transactions
        )

    @classmethod
    async def direct_debits(cls) -> DirectDebitSummary:
        direct_debits_count = await LoansAndRenewals.filter(
            type__name=LoansAndRenewalsEnum.SUBSCRIPTION.value
        ).count()

        direct_debits = (
            await LoansAndRenewals.annotate(total=Sum("payment_amount"))
            .filter(type__name=LoansAndRenewalsEnum.SUBSCRIPTION.value)
            .group_by("period__name")
            .all()
            .values("total", period="period__name")
        )

        monthly_cost = 0
        yearly_cost = 0

        for debit in direct_debits:
            if debit["period"] == "monthly":
                monthly_cost = debit["total"]
            if debit["period"] == "yearly":
                yearly_cost = debit["total"]

        return DirectDebitSummary(
            count=direct_debits_count,
            monthly_cost=monthly_cost,
            yearly_cost=yearly_cost,
        )

    @classmethod
    async def insurance(cls) -> list[Insurance]:
        insurance_renewals = (
            await LoansAndRenewals.filter(
                type__name=LoansAndRenewalsEnum.INSRUANCE.value
            )
            .prefetch_related("period")
            .order_by("end_date")
            .all()
        )

        return [
            Insurance(
                id=insurance.id,
                name=insurance.name,
                payment_amount=insurance.payment_amount,
                start_date=insurance.start_date,
                end_date=insurance.end_date,
                period=insurance.period.name,
                provider=insurance.provider,
                notes=insurance.notes,
            )
            for insurance in insurance_renewals
        ]

    @classmethod
    async def loan_portfolio(cls) -> LoanPortfolio:
        today = datetime.now(timezone.utc).replace(
            day=1, hour=00, minute=00, second=00, microsecond=00
        )
        loans_count = await LoansAndRenewals.filter(
            end_date__gt=today, type__name=LoansAndRenewalsEnum.LOAN.value
        ).count()

        loans = (
            await LoansAndRenewals.filter(
                end_date__gt=today, type__name=LoansAndRenewalsEnum.LOAN.value
            )
            .order_by("-end_date")
            .all()
        )

        if loans_count < 1:
            return LoanPortfolio(count=0, total_credit=0, accounts=[])

        total_credit = sum(loan.remaining_balance() for loan in loans)

        # Get the number of months from the loan which ends last
        # The first loan entity is the one furthest away based on the query to the DB.
        loan_end_date = loans[0].end_date
        logging.debug(f"Loan end date: {loan_end_date}")

        date_delta = relativedelta(loan_end_date, today)
        months_to_end_date = date_delta.years * 12 + date_delta.months

        # Go through the range from the months to end date
        # Generate an entity for each loan and the amount of the remaining balance for each one.
        data = []
        for month in range(months_to_end_date):
            data_entry = {
                "date": today if month == 0 else today + relativedelta(months=month)
            }
            for loan in loans:
                month_multiplier = month + 1
                calc_remaining_balance = loan.remaining_balance() - (
                    loan.payment_amount * month_multiplier
                )
                data_entry[loan.name] = (
                    calc_remaining_balance if calc_remaining_balance >= 0 else 0
                )
            data.append(data_entry)

        return LoanPortfolio(
            count=loans_count, total_credit=total_credit, accounts=data
        )

    @classmethod
    async def month_summary(
        cls,
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ) -> Month:
        if not months and not year and not specific_month:
            # Filters for income and bills for the entire of last month.
            last_month_end = datetime.now().replace(
                day=1, hour=23, minute=59, second=59, microsecond=59
            ) - relativedelta(days=1)
            last_month_start = last_month_end.replace(
                day=1, hour=00, minute=00, second=00, microsecond=00
            )
        else:
            # TODO finish this
            # if not current month use the previous month summaries to work it out
            logging.debug("not current month")
            last_month_end = datetime.now().replace(
                day=1, hour=23, minute=59, second=59, microsecond=59
            ) - relativedelta(days=1)
            last_month_start = last_month_end.replace(
                day=1, hour=00, minute=00, second=00, microsecond=00
            )

        bills_query = (
            await YnabTransactions.annotate(bills=Sum("amount"))
            .filter(
                Q(category_fk__category_group_name__in=cls.EXCLUDE_EXPENSE_NAMES),
                Q(date__gte=last_month_start),
                Q(date__lt=last_month_end),
                Q(debit=True),
            )
            .group_by("cleared")
            .first()
            .values("bills")
        )

        bills = bills_query.get("bills")

        income_query = (
            await YnabTransactions.filter(
                Q(payee_name="BJSS LIMITED"),
                Q(date__gte=last_month_start),
                Q(date__lt=last_month_end),
                Q(debit=False),
            )
            .first()
            .values("amount")
        )
        income = income_query.get("amount")

        logging.debug(f"Income: {income}. Bills: {bills}")

        # update the from date to the beginning of the month for everything spent so far.
        this_month_start = last_month_start + relativedelta(months=1)
        this_month_end = last_month_end + relativedelta(months=1)

        categories = (
            await YnabTransactions.annotate(spent=Sum("amount"))
            .filter(
                category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
                date__gte=this_month_start,
                date__lt=this_month_end,
                transfer_account_id__isnull=True,
                debit=True,
            )
            .group_by(
                "category_fk__category_group_name",
                "category_name",
                "category_fk__budget__amount",
            )
            .all()
            .values(
                "spent",
                name="category_name",
                group="category_fk__category_group_name",
                budget="category_fk__budget__amount",
            )
        )
        # ex output:
        # [{'name': 'Coffee', 'group': 'Frequent', 'spent': -9950.0, 'budget': 50},
        # {'name': 'Restaurants', 'group': 'Frequent', 'spent': -6000.0, 'budget': 50}]

        categories = sorted(categories, key=lambda x: x["spent"], reverse=True)

        balance_spent = 0
        balance_budget = 0

        for category in categories:
            if category["budget"] is None:
                category["budget"] = 0
            balance_spent += category.get("spent")
            balance_budget += category.get("budget")

        logging.debug(f"Total spent this month: {balance_spent}")
        logging.debug(f"Total budgeted: {balance_budget}")

        savings = await Savings.filter(
            date__gte=this_month_start, date__lt=this_month_end
        ).first()
        savings_milliunit = savings.target * 1000 if savings else 0
        logging.debug(f"Savings target: {savings_milliunit}")

        balance_available = (income - (balance_spent + bills)) - savings_milliunit
        logging.debug(f"Balance available: {balance_available}")

        days_left = await YnabHelpers.get_days_left_from_current_month()
        daily_spend = balance_available / days_left

        uncategorised_transactions = await YnabTransactions.filter(
            category_fk_id=None, transfer_account_id=None
        ).count()

        notification_text = (
            f"{uncategorised_transactions} uncategorised transactions"
            if uncategorised_transactions > 1
            else (
                "1 uncategorised transaction"
                if uncategorised_transactions > 0
                else None
            )
        )

        upcoming_renewals = (
            await LoansAndRenewals.filter(
                Q(period__name="yearly"),
                Q(end_date__isnull=True),
                Q(
                    Q(start_date__month=this_month_start.month)
                    | Q(start_date__month=this_month_start.month + 1)
                ),
            )
            .all()
            .values("name", amount="payment_amount", date="start_date")
        )

        return Month(
            notif=notification_text,
            summary={
                "days_left": days_left,
                "balance_available": balance_available,
                "balance_spent": balance_spent,
                "balance_budget": balance_budget,
                "daily_spend": daily_spend,
            },
            renewals=upcoming_renewals,
            categories=categories[0:3],
            income_expenses={
                "income": income,
                "bills": bills,
                "balance_spent": balance_spent,
                "balance_available": balance_available,
                "savings": savings_milliunit,
            },
        )

    @classmethod
    async def refunds(cls) -> Refunds:
        refunds_count = await YnabTransactions.filter(
            debit=False, category_fk__category_group_name__in=cls.CAT_EXPENSE_NAMES
        ).count()

        refunds = (
            await YnabTransactions.filter(
                debit=False, category_fk__category_group_name__in=cls.CAT_EXPENSE_NAMES
            )
            .order_by("date", "-amount")
            .all()
            .values(
                "id",
                "account_id",
                "amount",
                "account_name",
                "date",
                category="category_fk__category_group_name",
                subcategory="category_name",
                payee="payee_name",
            )
        )

        return Refunds(count=refunds_count, transactions=refunds)

    @classmethod
    async def transaction_summary(
        cls,
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ) -> TransactionSummary:
        if not months and not year and not specific_month:
            # Filters for transactions for the entire of last month.
            month_end = (
                datetime.now().replace(
                    day=1, hour=23, minute=59, second=59, microsecond=59
                )
                - relativedelta(days=1)
                + relativedelta(months=1)
            )
            month_start = month_end.replace(
                day=1, hour=00, minute=00, second=00, microsecond=00
            )
        else:
            # TODO finish this
            month_end = (
                datetime.now().replace(
                    day=1, hour=23, minute=59, second=59, microsecond=59
                )
                - relativedelta(days=1)
                + relativedelta(months=1)
            )
            month_start = month_end.replace(
                day=1, hour=00, minute=00, second=00, microsecond=00
            )

        db_accounts = await YnabAccounts.all().values("id", "name")
        accounts_match = {
            db_account["name"]: db_account["id"] for db_account in db_accounts
        }

        transactions = (
            await YnabTransactions.filter(
                category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
                date__gte=month_start,
                date__lt=month_end,
                transfer_account_id__isnull=True,
                debit=True,
            )
            .order_by("-date")
            .all()
            .values(
                "id",
                "account_id",
                "amount",
                "account_name",
                "date",
                category="category_fk__category_group_name",
                subcategory="category_name",
                payee="payee_name",
            )
        )

        card_types = ["BA AMEX", "Barclays CC", "HSBC CC", "HSBC ADVANCE"]
        amex_balance = sum(
            transaction["amount"] if transaction["account_name"] == "BA AMEX" else 0
            for transaction in transactions
        )
        barclays_balance = sum(
            transaction["amount"] if transaction["account_name"] == "Barclays CC" else 0
            for transaction in transactions
        )
        hsbc_cc_balance = sum(
            transaction["amount"] if transaction["account_name"] == "HSBC CC" else 0
            for transaction in transactions
        )
        hsbc_adv_balance = sum(
            (
                transaction["amount"]
                if transaction["account_name"] == "HSBC ADVANCE"
                else 0
            )
            for transaction in transactions
        )
        misc_balance = sum(
            (
                transaction["amount"]
                if transaction["account_name"] not in card_types
                else 0
            )
            for transaction in transactions
        )

        if misc_balance > 0:
            logging.warning("Transactions not in account list.")

        total_balance = (
            amex_balance + barclays_balance + hsbc_cc_balance + hsbc_adv_balance
        )

        accounts = [
            {
                "id": accounts_match["BA AMEX"],
                "name": "BA AMEX",
                "balance": amex_balance,
            },
            {
                "id": accounts_match["HSBC CC"],
                "name": "HSBC CC",
                "balance": hsbc_cc_balance,
            },
            {
                "id": accounts_match["HSBC ADVANCE"],
                "name": "HSBC ADVANCE",
                "balance": hsbc_adv_balance,
            },
            {
                "id": accounts_match["Barclays CC"],
                "name": "Barclays CC",
                "balance": barclays_balance,
            },
        ]

        return TransactionSummary(
            summary={"total": total_balance, "accounts": accounts},
            transactions=transactions,
        )

    @classmethod
    async def upcoming_bills(cls) -> UpcomingBills:
        # Bills should not change on a regular basis, so just look at all the bills from the last month.
        last_month_end = datetime.now().replace(
            day=1, hour=23, minute=59, second=59, microsecond=59
        ) - relativedelta(days=1)
        last_month_start = last_month_end.replace(
            day=1, hour=00, minute=00, second=00, microsecond=00
        )

        bills = (
            await YnabTransactions.annotate(total=Sum("amount"))
            .filter(
                Q(category_fk__category_group_name__in=cls.EXCLUDE_EXPENSE_NAMES),
                Q(date__gte=last_month_start),
                Q(date__lt=last_month_end),
                Q(debit=True),
            )
            .group_by("category_name", "category_fk__category_group_name")
            .order_by("-total")
            .all()
            .values(
                "total",
                name="category_name",
                category="category_fk__category_group_name",
            )
        )

        total_bills = sum(bill["total"] for bill in bills)

        return UpcomingBills(total=total_bills, subcategories=bills)

    @classmethod
    async def upcoming_bills_details(cls) -> list[UpcomingBillsDetails]:
        last_month_end = datetime.now().replace(
            day=1, hour=23, minute=59, second=59, microsecond=59
        ) - relativedelta(days=1)
        last_month_start = last_month_end.replace(
            day=1, hour=00, minute=00, second=00, microsecond=00
        )

        bills = (
            await YnabTransactions.filter(
                Q(category_fk__category_group_name__in=cls.EXCLUDE_EXPENSE_NAMES),
                Q(date__gte=last_month_start),
                Q(date__lt=last_month_end),
                Q(debit=True),
            )
            .order_by("date", "-amount")
            .all()
            .values(
                "amount",
                "date",
                "memo",
                payee="payee_name",
                name="category_name",
                category="category_fk__category_group_name",
            )
        )

        return [UpcomingBillsDetails(**bill) for bill in bills]
