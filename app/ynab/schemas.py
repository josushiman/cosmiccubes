from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, computed_field
from datetime import date as date_field


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
    def status(self) -> float:
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
    def status(self) -> float:
        if self.spent > self.budgeted:
            return "overspent"
        return "on track"


class BudgetsSummary(BaseModel):
    total: Optional[float] = 0.0
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


class CreditSummary(BaseModel):
    total: float
    accounts: List[CardBalance]

    @field_validator("total")
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


class TransactionSummary(BaseModel):
    summary: CreditSummary
    transactions: List[Transaction]


class Refunds(BaseModel):
    count: int
    transactions: List[Transaction]


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


class BillCategory(BaseModel):
    name: str
    amount: float

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class LoanRenewalCategory(BaseModel):
    name: str
    date: date_field
    amount: float


class CategoryTrends(BaseModel):
    period: str
    trend: str
    avg_spend: float
    percentage: float | str

    @field_validator("avg_spend")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class CategoryTransactions(BaseModel):
    total: float
    trends: List[CategoryTrends]
    transactions: List[Transaction]

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


class UpcomingBills(BaseModel):
    total: float
    total_bills: float
    total_loans: Optional[float] = 0.0
    total_renewals: Optional[float] = 0.0
    bills: List[BillCategory]
    loans: Optional[List[LoanRenewalCategory]] = None
    renewals: Optional[List[LoanRenewalCategory]] = None


class UpcomingBillsDetails(BaseModel):
    amount: float
    date: date_field
    memo: Optional[str]
    payee: str
    name: str
    category: str

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


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
