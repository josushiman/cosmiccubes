from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from datetime import date as date_field

class GoalTypeEnum(Enum):
    TB = 'TB'
    TBD = 'TBD'
    MF = 'MF'
    NEED = 'NEED'
    DEBT = 'DEBT'

class AvailableBalance(BaseModel):
    total: float = Field(..., description='Total balance currently available across all accounts.')
    spent: float = Field(..., description='The total spent across all accounts.')
    available: float = Field(..., description='The left over balance after all outstanding credit is paid off.')

class CardBalance(BaseModel):
    name: str = Field(..., description='Account name for the card.')
    balance: float = Field(..., description='Current balance of the card.')
    cleared: float = Field(..., description='All transactions which have been cleared.')
    uncleared: float = Field(..., description='All transactions which are currently uncleared.')

class CardBalances(BaseModel):
    data: List[CardBalance]

class Transaction(BaseModel):
    payee: str = Field(..., description='Name of the merchant.')
    amount: float = Field(..., description='Amount that was charged against the transaction.')
    date: date_field = Field(..., description='Date of the transaction being cleared.')
    subcategory: str = Field(..., description='Subcategory of the transaction.')

class LastXTransactions(BaseModel):
    since_date: date_field
    data: List[Transaction]

class TotalSpent(BaseModel):
    since_date: date_field
    total: float = Field(..., description='Total amount spent across all accounts from the since_date to today.')

# TODO do all of them