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


class CategorySummary(BaseModel):
    id: UUID
    category: str
    amount: float
    budgeted: float = 0.0
    status: Optional[str] = None
    subcategories: List[SubCategorySummary]

    @field_validator("amount")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        if value is None:
            return 0
        return value / 1000.0


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


class MonthCategory(BaseModel):
    name: str
    group: Optional[str] = None
    spent: float
    budget: float

    @field_validator("spent")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


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


class UpcomingRenewal(BaseModel):
    name: str
    date: date_field
    amount: float


class Month(BaseModel):
    notif: str | None
    summary: MonthSummary
    renewals: Optional[List[UpcomingRenewal]] = None
    categories: List[MonthCategory]
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
    category: str
    total: float

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


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
    subcategories: List[BillCategory]

    @field_validator("total")
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0


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
