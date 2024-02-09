from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, validator, computed_field
from datetime import date as date_field
from app.ynab.models import TransactionDetail

class AvailableBalanceResponse(BaseModel):
    total: float = Field(..., description='Total balance currently available across all accounts.')
    spent: float = Field(..., description='The total spent across all accounts.')
    available: float = Field(..., description='The left over balance after all outstanding credit is paid off.')

    @validator("total", "spent", "available", pre=True)
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0

class CardBalance(BaseModel):
    name: str = Field(..., description='Account name for the card.')
    balance: float = Field(..., description='Current balance of the card.')
    cleared: float = Field(..., description='All transactions which have been cleared.')
    uncleared: float = Field(..., description='All transactions which are currently uncleared.')

    @validator("balance", "cleared", "uncleared", pre=True)
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0

class CardBalancesResponse(BaseModel):
    data: List[CardBalance]

class CategorySpent(BaseModel):
    name: str
    spent: float
    budget: float

    @computed_field
    @property
    def progress(self) -> float:
        if self.budget == 0: return 0
        return (self.spent / self.budget) * 100
    
    @validator("spent", "budget", pre=True)
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0

class CategorySpentResponse(BaseModel):
    since_date: date_field
    data: List[CategorySpent]

class CreditAccount(BaseModel):
    id: Optional[UUID] = None
    date: Optional[date_field] = None
    amount: Optional[float] = None
    account_name: str

class CreditAccountResponse(BaseModel):
    since_date: date_field
    data: List[CreditAccount]

class EarnedVsSpentResponse(BaseModel):
    since_date: date_field
    earned: float
    spent: float

    @validator("spent", "earned", pre=True)
    def format_milliunits(cls, value):
        # Convert the integer value to milliunits (assuming it's in microunits)
        return value / 1000.0

class IncomeVsExpense(BaseModel):
    month: str
    year: str
    income: float
    expenses: float

class IncomeVsExpensesResponse(BaseModel):
    since_date: date_field
    data: List[IncomeVsExpense]

class SpentInPeriodResponse(BaseModel):
    spent: float

class SpentVsBudgetResponse(BaseModel):
    balance: float
    budget: float
    spent: float
    progress: float

class SubCategorySpentResponse(BaseModel):
    since_date: date_field
    data: List[CategorySpent]

class Transaction(BaseModel):
    payee: str = Field(..., description='Name of the merchant.')
    amount: float = Field(..., description='Amount that was charged against the transaction.')
    date: date_field = Field(..., description='Date of the transaction being cleared.')
    subcategory: str = Field(..., description='Subcategory of the transaction.')

class LastXTransactions(BaseModel):
    since_date: date_field
    data: List[Transaction]

class TotalSpentResponse(BaseModel):
    since_date: date_field
    total: float = Field(..., description='Total amount spent across all accounts from the since_date to today.')

class TransactionsByFilterResponse(BaseModel):
    since_date: date_field
    data: List[TransactionDetail]
# TODO change the above for payee, category and account types
    
class TransactionByMonth(BaseModel):
    month: int
    month_long: str
    month_short: str
    total_spent: float
    total_earned: float

class TransactionsByMonthResponse(BaseModel):
    since_date: date_field
    data: List[TransactionByMonth]
