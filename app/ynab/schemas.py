from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, computed_field
from datetime import date as date_field


class Transaction(BaseModel):
    id: UUID
    account_id: UUID
    payee: str = Field(..., description="Name of the merchant.")
    amount: float = Field(
        ..., description="Amount that was charged against the transaction."
    )
    date: date_field = Field(..., description="Date of the transaction being cleared.")
    category: str | None = Field(..., description="Category of the transaction.")
    subcategory: str | None = Field(..., description="Subcategory of the transaction.")

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class CardBill(BaseModel):
    date: date_field
    ba_amex: Optional[float] = Field(default=0.0, alias="BA AMEX")
    hsbc_cc: Optional[float] = Field(default=0.0, alias="HSBC CC")
    barclays_cc: Optional[float] = Field(default=0.0, alias="Barclays CC")

    @field_validator("ba_amex", "hsbc_cc", "barclays_cc")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0

    @computed_field
    @property
    def total(self) -> float:
        return self.ba_amex + self.hsbc_cc + self.barclays_cc


class CatBudgetReq(BaseModel):
    name: str
    count: int
    subcategories: List[str]


class BudgetsNeeded(BaseModel):
    count: int
    categories: Optional[List[CatBudgetReq]] = []


class SubCatBudgetSummary(BaseModel):
    name: str
    budgeted: float
    spent: float

    @field_validator("spent")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0

    @computed_field
    @property
    def status(self) -> str:
        if self.spent > self.budgeted:
            return "overspent"
        return "on track"


class CatBudgetSummary(BaseModel):
    name: str
    budgeted: float
    spent: float
    on_track: Optional[int] = 0
    overspent: Optional[int] = 0
    subcategories: List[SubCatBudgetSummary]

    @computed_field
    @property
    def status(self) -> str:
        if self.spent > self.budgeted:
            return "overspent"
        return "on track"


class BudgetsDashboard(BaseModel):
    total: Optional[float] = 0.0
    on_track: Optional[int] = 0
    overspent: Optional[int] = 0
    needed: Optional[int] = 0
    categories: Optional[List[CatBudgetSummary]] = []


class CardBalance(BaseModel):
    id: UUID
    name: str = Field(..., description="Account name for the card.")
    balance: float = Field(..., description="Current balance of the card.")

    @field_validator("balance")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class CategorySpent(BaseModel):
    name: str
    spent: float
    budget: Optional[float] = None
    total_spent: Optional[float] = None

    @computed_field
    @property
    def progress(self) -> float:
        if self.budget is None and self.total_spent is None:
            return None
        if self.budget and self.budget != 0:
            return (self.spent / self.budget) * 100
        elif self.total_spent and self.total_spent != 0:
            return (self.spent / self.total_spent) * 100
        return 0

    @field_validator("spent", "budget", "total_spent")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class SubCategorySummary(BaseModel):
    name: str
    amount: float
    budgeted: float = 0.0

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        if value is None:
            return 0
        return value / 1000.0

    @computed_field
    @property
    def progress(self) -> float:
        if self.budgeted is None and self.amount is None:
            return None
        if self.amount >= self.budgeted:
            return 100
        if self.budgeted and self.budgeted != 0:
            return (self.amount / self.budgeted) * 100
        return 0

    @computed_field
    @property
    def status(self) -> str:
        if self.amount > self.budgeted:
            return "overspent"
        return "on track"


class CategorySummary(BaseModel):
    id: Optional[UUID] = None
    category: Optional[str] = None
    amount: float
    budgeted: float = 0.0
    subcategories: List[SubCategorySummary]

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        if value is None:
            return 0
        return value / 1000.0

    @computed_field
    @property
    def status(self) -> str:
        if self.amount > self.budgeted:
            return "overspent"
        return "on track"


class CreditAccount(BaseModel):
    id: Optional[UUID] = None
    date: Optional[date_field] = None
    amount: Optional[float] = None
    account_name: str

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        if value is None:
            return 0
        return value / 1000.0


class Refunds(BaseModel):
    count: int = 0
    total: float = 0.0
    transactions: Optional[List[Transaction]] = []

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


# TODO clean up the transaction details to be a separate class
class TransactionSummary(BaseModel):
    total: float
    accounts: List[CardBalance]
    transactions: List[Transaction]
    average_purchase: float
    transaction_count: int
    biggest_purchase: Optional[Transaction] = None
    refunds: Refunds

    @field_validator("total", "average_purchase")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class DirectDebitSummary(BaseModel):
    count: int
    monthly_cost: float
    yearly_cost: float


class IncomeVsExpense(BaseModel):
    month: str
    year: str
    income: float
    expenses: float

    @field_validator("income", "expenses")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class Insurance(BaseModel):
    id: UUID
    name: str
    payment_amount: float
    start_date: date_field
    end_date: Optional[date_field] = None
    period: Optional[str] = None
    provider: Optional[str] = None
    notes: Optional[str] = None


class LoanPortfolio(BaseModel):
    count: int
    total_credit: float
    accounts: List[dict]


class MonthIncomeExpenses(BaseModel):
    balance_available: float
    balance_spent: float
    income: float
    bills: float
    savings: float

    @field_validator("balance_available", "balance_spent", "income", "bills", "savings")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class MonthSummary(BaseModel):
    days_left: int
    balance_available: float
    balance_spent: float
    balance_budget: float
    daily_spend: float

    @field_validator("balance_available", "balance_spent", "daily_spend")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class Month(BaseModel):
    notif: str | None
    summary: MonthSummary
    income_expenses: MonthIncomeExpenses


class SubCategorySpentResponse(BaseModel):
    since_date: date_field
    data: List[CategorySpent]


class TransactionByMonth(BaseModel):
    month_long: str
    month_short: str
    total_spent: float
    total_earned: float

    @field_validator("total_spent", "total_earned")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class TransactionsByMonthResponse(BaseModel):
    since_date: date_field
    data: List[TransactionByMonth]


class BillTransaction(BaseModel):
    memo: Optional[str] = None
    payee: str = Field(..., description="Name of the merchant.")
    amount: float = Field(
        ..., description="Amount that was charged against the transaction."
    )
    date: date_field = Field(..., description="Date of the transaction being cleared.")
    subcategory: str | None = Field(..., description="Subcategory of the transaction.")

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class BillCategory(BaseModel):
    name: str
    amount: float
    transactions: List[BillTransaction]

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class LoanRenewalCategory(BaseModel):
    name: str
    date: date_field
    amount: float


class LoanRenewalCounts(BaseModel):
    insurance: int = 0
    loans: int = 0
    subscriptions: int = 0


class LoanRenewalTotals(BaseModel):
    credit: float = 0.0
    insurance: float = 0.0
    loans: float = 0.0
    renewals: float = 0.0
    subscriptions: float = 0.0


class LoanRenewalOverview(BaseModel):
    counts: LoanRenewalCounts
    totals: LoanRenewalTotals


class CategoryTrends(BaseModel):
    period: str
    trend: str
    avg_spend: float
    percentage: float | str

    @field_validator("avg_spend")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class CategoryTrendItem(BaseModel):
    month: str
    total: float

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class CategoryTrendSummary(BaseModel):
    data: Optional[List[CategoryTrendItem]] = []
    summary: List[CategoryTrends]


class CategoryTransactions(BaseModel):
    total: float
    on_track: Optional[bool] = None
    budget: float
    trends: CategoryTrendSummary

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class UpcomingBills(BaseModel):
    total: float
    total_bills: float
    count_bills: int
    total_loans: Optional[float] = 0.0
    total_renewals: Optional[float] = 0.0
    bills: List[BillCategory]
    loans: Optional[List[LoanRenewalCategory]] = None
    renewals: Optional[List[LoanRenewalCategory]] = None


class PastBillsSummary(BaseModel):
    last_month_diff: float
    last_month_trend: float
    avg_trend: float


class PastBills(BaseModel):
    summary: PastBillsSummary
    data: List[CardBill]


class MonthSavingsCalc(BaseModel):
    total: float

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class DailySpendItem(BaseModel):
    date: date_field
    total: Optional[float] = 0.0
    transactions: Optional[List[Transaction]] = []

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class DailySpendSummary(BaseModel):
    total: float
    days: List[DailySpendItem]


class Payee(BaseModel):
    payee_name: str
    count: int
    total: float

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class PayeeSummary(BaseModel):
    count: int = 0
    topspender: Optional[Payee] = None
    data: List[Payee] = []
