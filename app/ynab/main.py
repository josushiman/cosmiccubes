import logging
from calendar import monthrange
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from tortoise.functions import Sum
from tortoise.expressions import Q
from app.ynab.helpers import YnabHelpers
from app.ynab.serverknowledge import YnabServerKnowledgeHelper
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
    CardPayments,
    Savings,
    LoansAndRenewals,
)
from app.ynab.schemas import (
    Month,
    TransactionSummary,
    CategorySummary,
    SubCategorySummary,
    BudgetsNeeded,
    BudgetsDashboard,
    SubCatBudgetSummary,
    UpcomingBills,
    CategoryTransactions,
    LoanPortfolio,
    DirectDebitSummary,
    Insurance,
    Refunds,
    MonthSavingsCalc,
    DailySpendItem,
    DailySpendSummary,
    Transaction,
    CardBill,
)


class YNAB:
    CAT_EXPENSE_NAMES = ["Frequent", "Giving", "Non-Monthly Expenses", "Work"]
    EXCLUDE_EXPENSE_NAMES = ["Monthly Bills", "Loans", "Credit Card Payments"]
    INCLUDE_INCOME = "Internal Master Category"
    INCLUDE_EXPENSE_NAMES = ["Monthly Bills", "Loans"]
    EXCLUDE_CATS = [
        "Monthly Bills",
        "Loans",
        "Credit Card Payments",
        "Internal Master Category",
    ]
    EXCLUDE_BUDGETS = [
        "Monthly Bills",
        "Yearly Bills",
        "Loans",
        "Credit Card Payments",
        "Internal Master Category",
        "Non-Monthly Expenses",
        "Saving Goals",
        "Holidays",
    ]

    @classmethod
    async def average_card_bill(
        cls, months: PeriodMonthOptionsIntEnum = None
    ) -> list[CardBill]:
        months = 3 if not months else months.value
        today = datetime.now().replace(
            day=1, hour=00, minute=00, second=00, microsecond=00
        )
        start_date = today - relativedelta(months=months)

        card_payments = (
            await CardPayments.filter(transaction__date__gte=start_date)
            .all()
            .prefetch_related("account", "transaction")
            .order_by("transaction__date")
        )

        # Get the number of months from the first bill to today
        date_delta = relativedelta(today, start_date)
        months_to_start_date = date_delta.years * 12 + date_delta.months

        # Go through the range from the months to start date
        # Generate an entity for each bill and the amount of the bill.
        data = []
        for month in range(months_to_start_date):
            # Skip the current month as there won't be a bill yet.
            if month == 0:
                continue

            data_entry = {
                "date": today if month == 0 else today - relativedelta(months=month)
            }
            for payment in card_payments:
                if (
                    payment.transaction.date.month == data_entry["date"].month
                    and payment.transaction.date.year == data_entry["date"].year
                ):
                    data_entry[payment.account.name] = payment.transaction.amount
            data.append(CardBill(**data_entry))

        reverse_data = sorted(data, key=lambda item: item.date, reverse=False)
        return reverse_data

    @classmethod
    async def budgets_dashboard(cls) -> BudgetsDashboard:
        budgets = await Budgets.all().prefetch_related("category")

        grouped_categories = {}
        for item in budgets:
            category = item.category.category_group_name
            name = item.category.name
            budgeted = item.amount
            spent = item.category.activity
            grouped_categories.setdefault(category, []).append(
                {"name": name, "budgeted": budgeted, "spent": spent}
            )

        raw_results = []
        for category, subcats in grouped_categories.items():
            total_budgeted = 0
            total_spent = 0
            total_subcats_on_track = 0
            total_subcats_overspent = 0
            for subcat in subcats:
                pydantic_subcat = SubCatBudgetSummary(**subcat)
                total_budgeted += pydantic_subcat.budgeted
                total_spent += pydantic_subcat.spent
                total_subcats_on_track += (
                    1 if pydantic_subcat.status == "on track" else 0
                )
                total_subcats_overspent += (
                    1 if pydantic_subcat.status != "on track" else 0
                )

            raw_results.append(
                {
                    "name": category,
                    "budgeted": total_budgeted,
                    "spent": total_spent,
                    "on_track": total_subcats_on_track,
                    "overspent": total_subcats_overspent,
                    "subcategories": subcats,
                }
            )

        total_budgeted = sum(cat["budgeted"] for cat in raw_results)
        total_on_track = sum(cat["on_track"] for cat in raw_results)
        total_overspent = sum(cat["overspent"] for cat in raw_results)

        results = sorted(raw_results, key=lambda x: x["spent"], reverse=True)

        return BudgetsDashboard(
            total=total_budgeted,
            on_track=total_on_track,
            overspent=total_overspent,
            categories=results,
        )

    @classmethod
    async def budgets_needed(cls) -> BudgetsNeeded:
        categories_count = await YnabCategories.filter(
            category_group_name__not_in=cls.EXCLUDE_BUDGETS,
            budget__isnull=True,
        ).count()

        categories = (
            await YnabCategories.filter(
                category_group_name__not_in=cls.EXCLUDE_BUDGETS,
                budget__isnull=True,
            )
            .all()
            .values("name", category="category_group_name")
        )

        if categories_count == 0:
            return BudgetsNeeded(count=0, categories=[])

        grouped_categories = {}
        for item in categories:
            category = item["category"]
            name = item["name"]
            grouped_categories.setdefault(category, []).append(name)

        results = []
        for category, names in grouped_categories.items():
            results.append(
                {"name": category, "count": len(names), "subcategories": names}
            )

        results = sorted(results, key=lambda x: x["count"], reverse=True)

        return BudgetsNeeded(count=categories_count, categories=results)

    @classmethod
    async def categories_summary(
        cls,
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ) -> list[CategorySummary]:
        start_date, end_date = await YnabHelpers.get_dates_for_transaction_queries(
            year=year, months=months, specific_month=specific_month
        )

        categories = (
            await YnabTransactions.annotate(spent=Sum("amount"))
            .filter(
                category_fk__category_group_name__isnull=False,
                category_fk__category_group_name__not_in=cls.EXCLUDE_CATS,
                date__gte=start_date,
                date__lte=end_date,
                debit=True,
            )
            .prefetch_related("category_fk")
            .group_by(
                "category_id",
                "category_name",
                "category_fk__category_group_id",
                "category_fk__category_group_name",
            )
            .order_by("-spent")
            .values(
                "spent",
                id="category_fk__category_group_id",
                name="category_fk__category_group_name",
                subcategory="category_name",
                subcategory_id="category_id",
            )
        )
        # Example output:
        #   [{
        #       'id': UUID('b648037e-29f8-4d02-ac00-9e71ba409af6'), 'name': 'Frequent', 'subcategory': 'Other Shopping',
        #       'subcategory_id': UUID('6fad4995-fb1d-4620-bd22-4fcba391a5df'), 'spent': 69000
        #   }...]

        budget_multiplier = await YnabHelpers.months_between(
            start_date=start_date, end_date=end_date, months=months
        )

        budget_entities = await Budgets.all()
        budgets = {
            budget.category_id: (budget.amount * budget_multiplier)
            for budget in budget_entities
        }

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
                subcategories=[
                    SubCategorySummary(**subcat) for subcat in summary["subcategories"]
                ],
            )
            category_summaries.append(category_summary)

        return category_summaries

    @classmethod
    async def category_summary(
        cls,
        category_name: str,
        subcategory_name: str,
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ) -> CategoryTransactions:
        start_date, end_date = await YnabHelpers.get_dates_for_transaction_queries(
            year=year, months=months, specific_month=specific_month
        )

        subcategory_name = subcategory_name.replace("-", " ")

        transactions = (
            await YnabTransactions.filter(
                category_fk__category_group_name__iexact=category_name,
                category_name__iexact=subcategory_name,
                date__gte=start_date,
                date__lte=end_date,
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

        category_spent = sum(transaction["amount"] for transaction in transactions)

        this_month_start = datetime.now().replace(
            day=1, hour=00, minute=00, second=00, microsecond=00
        )
        last_month_start = this_month_start - relativedelta(months=1)
        last_3_month_start = this_month_start - relativedelta(months=3)
        last_6_month_start = this_month_start - relativedelta(months=6)
        last_month_end = this_month_start - relativedelta(days=1)

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

            try:
                # TODO trend percentage is not good when searching over multiple months.
                trend_percentage = round(
                    ((category_spent - average_spend) / average_spend) * 100
                )
                logging.debug(f"Test trend percentage: {trend_percentage}")
            except ZeroDivisionError:
                trend_percentage = 0
                pass

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
                    "percentage": (
                        trend_percentage if trend_percentage > 0 else -trend_percentage
                    ),
                }
            )

        return CategoryTransactions(
            total=category_spent, trends=trends, transactions=transactions
        )

    @classmethod
    async def daily_spend(cls, num_days: int) -> DailySpendSummary:
        start_date = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - relativedelta(days=num_days)

        end_date = datetime.now()

        transactions = (
            await YnabTransactions.annotate(total=Sum("amount"))
            .filter(
                date__gte=start_date,
                category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
                debit=True,
                transfer_account_id__isnull=True,
            )
            .group_by("date")
            .values("total", "date")
        )

        all_dates = [
            (start_date + relativedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((end_date - start_date).days + 1)
        ]
        logging.debug(f"Dates generated for the last {num_days} days: {all_dates}")

        # Convert fetched transaction data into a dictionary
        transaction_dict = {
            transaction["date"].strftime("%Y-%m-%d"): transaction["total"]
            for transaction in transactions
        }
        logging.debug(f"Transaction dict returned: {transaction_dict}")

        # Combine fetched transaction totals with all dates
        transaction_totals = [
            DailySpendItem(
                date=date,
                total=transaction_dict.get(date, 0),
                transactions=await cls.transaction_by_date(date=date),
            )
            for date in all_dates
        ]

        total = sum(date.total for date in transaction_totals)

        return DailySpendSummary(total=total, days=transaction_totals)

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
    async def last_period_salary(
        cls, start_date: datetime, end_date: datetime
    ) -> float:
        db_query = (
            YnabTransactions.filter(
                Q(payee_name="BJSS LIMITED"),
                Q(date__gte=start_date),
                Q(date__lte=end_date),
                Q(debit=False),
            )
            .first()
            .values("amount")
            .sql()
        )

        last_month_income = (
            await YnabTransactions.filter(
                Q(payee_name="BJSS LIMITED"),
                Q(date__gte=start_date),
                Q(date__lte=end_date),
                Q(debit=False),
            )
            .first()
            .values("amount")
        )

        logging.debug(db_query)

        try:
            return last_month_income.get("amount")
        except AttributeError:
            return 0.0

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
            .prefetch_related("period")
            .order_by("-end_date")
            .all()
        )

        if loans_count < 1:
            return LoanPortfolio(count=0, total_credit=0, accounts=[])

        total_credit = 0
        for loan in loans:
            total_credit += await YnabHelpers.remaining_balance(loan)

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
                calc_remaining_balance = await YnabHelpers.remaining_balance(loan) - (
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
        start_date, end_date = await YnabHelpers.get_dates_for_transaction_queries(
            year=year, months=months, specific_month=specific_month
        )

        spent_so_far = (
            await YnabTransactions.annotate(total=Sum("amount"))
            .filter(
                category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
                date__gte=start_date,
                date__lte=end_date,
                transfer_account_id__isnull=True,
                debit=True,
            )
            .group_by("debit")
            .first()
            .values("total")
        )

        try:
            balance_spent = spent_so_far.get("total")
        except AttributeError:
            balance_spent = 0.0

        budget_summary = await cls.budgets_dashboard()
        budget_multiplier = await YnabHelpers.months_between(
            start_date=start_date, end_date=end_date, months=months
        )

        balance_budget = budget_summary.total * budget_multiplier

        logging.debug(f"Total spent this month: {balance_spent}")
        logging.debug(f"Total budgeted: {balance_budget}")

        savings = await Savings.filter(date__gte=start_date, date__lte=end_date).first()
        savings_milliunit = savings.target * 1000 if savings else 0
        logging.debug(f"Savings target: {savings_milliunit}")

        # update the from date to the beginning of last month for bills and income
        last_month_start = start_date - relativedelta(months=1)
        last_month_end = start_date

        last_month_bills = await cls.upcoming_bills()

        try:
            bills = last_month_bills.total * 1000
        except AttributeError:
            bills = 0.0

        income = await cls.last_period_salary(
            start_date=last_month_start, end_date=last_month_end
        )

        logging.debug(f"Income: {income}. Bills: {bills}")

        balance_available = (income - (balance_spent + bills)) - savings_milliunit
        logging.debug(f"Balance available: {balance_available}")

        if (
            start_date.month == datetime.now().month
            and start_date.year == datetime.now().year
        ):
            days_left = await YnabHelpers.get_days_left_from_current_month()
            if days_left != 0:
                daily_spend = balance_available / days_left
            else:
                daily_spend = balance_available
        else:
            days_left = 0
            daily_spend = (
                balance_spent
                / monthrange(year=start_date.year, month=start_date.month)[1]
            )

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

        return Month(
            notif=notification_text,
            summary={
                "days_left": days_left,
                "balance_available": balance_available,
                "balance_spent": balance_spent,
                "balance_budget": balance_budget,
                "daily_spend": daily_spend,
            },
            income_expenses={
                "income": income,
                "bills": bills,
                "balance_spent": balance_spent,
                "balance_available": balance_available,
                "savings": savings_milliunit,
            },
        )

    @classmethod
    async def refunds(cls, 
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None
        ) -> Refunds:
        
        start_date, end_date = await YnabHelpers.get_dates_for_transaction_queries(
            year=year, months=months, specific_month=specific_month
        )

        refunds_count = await YnabTransactions.filter(
            debit=False,
            category_fk__category_group_name__in=cls.CAT_EXPENSE_NAMES,
            date__gte=start_date,
            date__lt=end_date,
        ).count()

        refunds = (
            await YnabTransactions.filter(
                debit=False,
                category_fk__category_group_name__in=cls.CAT_EXPENSE_NAMES,
                date__gte=start_date,
                date__lt=end_date,
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

        refund_total = sum(transaction["amount"] for transaction in refunds)

        return Refunds(count=refunds_count, transactions=refunds, total=refund_total)

    @classmethod
    async def savings(cls, year: SpecificYearOptionsEnum = None) -> list[Savings]:
        return await Savings.all().filter(date__year=year.value).order_by("date")

    @classmethod
    async def test_endpoint(
        cls,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ):

        return await YnabServerKnowledgeHelper.add_card_payments()

    @classmethod
    async def transaction_by_date(cls, date: str) -> list[Transaction]:
        date_datetime = datetime.strptime(date, "%Y-%m-%d")
        the_day_after = (date_datetime + relativedelta(days=1)).strftime("%Y-%m-%d")

        transactions = (
            await YnabTransactions.filter(
                date__gte=date,
                date__lte=the_day_after,
                category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
                debit=True,
                transfer_account_id__isnull=True,
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

        logging.debug(f"Found {len(transactions)} transactions for {date}")

        return [Transaction(**transaction) for transaction in transactions]

    @classmethod
    async def transaction_summary(
        cls,
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ) -> TransactionSummary:
        start_date, end_date = await YnabHelpers.get_dates_for_transaction_queries(
            year=year, months=months, specific_month=specific_month
        )

        db_accounts = await YnabAccounts.all().values("id", "name")
        accounts_match = {
            db_account["name"]: db_account["id"] for db_account in db_accounts
        }

        transactions = (
            await YnabTransactions.filter(
                category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
                date__gte=start_date,
                date__lte=end_date,
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

        biggest_purchase = (
            await YnabTransactions.filter(
                category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
                date__gte=start_date,
                date__lte=end_date,
                transfer_account_id__isnull=True,
                debit=True,
            )
            .order_by("-amount")
            .limit(1)
            .first()
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

        refunds = await cls.refunds(year=year, months=months, specific_month=specific_month)

        total_balance = (
            amex_balance + barclays_balance + hsbc_cc_balance + hsbc_adv_balance
        ) - refunds.total

        transaction_count = await YnabTransactions.filter(
            category_fk__category_group_name__not_in=cls.EXCLUDE_EXPENSE_NAMES,
            date__gte=start_date,
            date__lte=end_date,
            transfer_account_id__isnull=True,
            debit=True,
        ).count()

        average_purchase = total_balance / transaction_count

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
            total=total_balance,
            accounts=accounts,
            average_purchase=average_purchase,
            transaction_count=transaction_count,
            biggest_purchase=biggest_purchase,
            transactions=transactions,
            refunds=refunds,
        )

    @classmethod
    async def upcoming_bills(
        cls,
        months: PeriodMonthOptionsIntEnum = None,
        year: SpecificYearOptionsEnum = None,
        specific_month: SpecificMonthOptionsEnum = None,
    ) -> UpcomingBills:
        # Bills should not change on a regular basis, so just look at all the bills from the last month.
        last_month_end = datetime.now().replace(
            day=1, hour=23, minute=59, second=59, microsecond=59
        ) - relativedelta(days=1)
        last_month_start = last_month_end.replace(
            day=1, hour=00, minute=00, second=00, microsecond=00
        )

        monthly_bills = (
            await YnabTransactions.annotate(amount=Sum("amount"))
            .filter(
                category_fk__category_group_name="Monthly Bills",
                date__gte=last_month_start,
                date__lt=last_month_end,
                debit=True,
            )
            .group_by("category_name")
            .all()
            .values(
                "amount",
                name="category_name",
            )
        )

        monthly_bills_count = await YnabTransactions.filter(
            category_fk__category_group_name="Monthly Bills",
            date__gte=last_month_start,
            date__lt=last_month_end,
            debit=True,
        ).count()

        monthly_bills_summary = (
            await YnabTransactions.filter(
                category_fk__category_group_name="Monthly Bills",
                date__gte=last_month_start,
                date__lt=last_month_end,
                debit=True,
            )
            .order_by("date")
            .all()
            .values(
                "amount",
                "date",
                "memo",
                payee="payee_name",
                subcategory="category_name",
            )
        )

        for bill in monthly_bills:
            bill_transactions = []
            for bill_detail in monthly_bills_summary:
                if bill["name"] == bill_detail["subcategory"]:
                    bill_transactions.append(bill_detail)
            bill["transactions"] = bill_transactions

        loans_renewals = (
            await LoansAndRenewals.filter(
                type__name__in=["insurance", "loan", "subscription"]
            )
            .prefetch_related("type", "period")
            .order_by("start_date")
            .all()
        )

        loans = []
        renewals = []
        for loan_renewal in loans_renewals:
            renewal_this_month = await YnabHelpers.renewal_this_month(
                renewal_name=loan_renewal.name,
                renewal_start_date=loan_renewal.start_date,
                renewal_end_date=loan_renewal.end_date,
                renewal_type=loan_renewal.type.name,
                renewal_period=loan_renewal.period.name,
            )
            if renewal_this_month and loan_renewal.type.name in [
                "insurance",
                "subscription",
            ]:
                renewals.append(
                    {
                        "amount": loan_renewal.payment_amount,
                        "date": loan_renewal.start_date,
                        "name": loan_renewal.name,
                        "period": loan_renewal.period.name,
                        "category": "insurance",
                    }
                )
            elif renewal_this_month and loan_renewal.type.name == "loan":
                loans.append(
                    {
                        "amount": loan_renewal.payment_amount,
                        "date": loan_renewal.start_date,
                        "name": loan_renewal.name,
                        "period": loan_renewal.period.name,
                        "category": "loan",
                    }
                )

        total_bills = sum(bill["amount"] for bill in monthly_bills) / 1000
        total_loans = sum(loan["amount"] for loan in loans)
        total_renewals = sum(renewal["amount"] for renewal in renewals)

        total = total_bills + total_loans + total_renewals

        return UpcomingBills(
            total=total,
            total_bills=total_bills,
            count_bills=monthly_bills_count,
            total_loans=total_loans,
            total_renewals=total_renewals,
            bills=monthly_bills,
            loans=loans,
            renewals=renewals,
        )
