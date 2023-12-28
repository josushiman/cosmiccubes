from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class AccountType(Enum):
    checking = 'checking'
    savings = 'savings'
    cash = 'cash'
    creditCard = 'creditCard'
    lineOfCredit = 'lineOfCredit'
    otherAsset = 'otherAsset'
    otherLiability = 'otherLiability'
    mortgage = 'mortgage'
    autoLoan = 'autoLoan'
    studentLoan = 'studentLoan'
    personalLoan = 'personalLoan'
    medicalDebt = 'medicalDebt'
    otherDebt = 'otherDebt'

class GoalTypeEnum(Enum):
    TB = 'TB'
    TBD = 'TBD'
    MF = 'MF'
    NEED = 'NEED'
    DEBT = 'DEBT'

class CategoryGroup(BaseModel):
    id: UUID
    name: str
    hidden: bool = Field(..., description='Whether or not the category group is hidden')
    deleted: bool = Field(
        ...,
        description='Whether or not the category group has been deleted.  Deleted category groups will only be included in delta requests.',
    )

class CurrencyFormat(BaseModel):
    iso_code: str
    example_format: str
    decimal_digits: int
    decimal_separator: str
    symbol_first: bool
    group_separator: str
    currency_symbol: str
    display_symbol: bool

class Account(BaseModel):
    id: UUID
    name: str
    type: AccountType
    on_budget: bool = Field(..., description='Whether this account is on budget or not')
    closed: bool = Field(..., description='Whether this account is closed or not')
    note: Optional[str] = None
    balance: int = Field(
        ..., description='The current balance of the account in milliunits format'
    )
    cleared_balance: int = Field(
        ...,
        description='The current cleared balance of the account in milliunits format',
    )
    uncleared_balance: int = Field(
        ...,
        description='The current uncleared balance of the account in milliunits format',
    )
    transfer_payee_id: UUID = Field(
        ...,
        description='The payee id which should be used when transferring to this account',
    )
    direct_import_linked: Optional[bool] = Field(
        None,
        description='Whether or not the account is linked to a financial institution for automatic transaction import.',
    )
    direct_import_in_error: Optional[bool] = Field(
        None,
        description='If an account linked to a financial institution (direct_import_linked=true) and the linked connection is not in a healthy state, this will be true.',
    )
    last_reconciled_at: Optional[str] = Field(
        None, description='A date/time specifying when the account was last reconciled.'
    )
    debt_original_balance: Optional[int] = Field(
        None,
        description='The original debt/loan account balance, specified in milliunits format.',
    )
    debt_interest_rates: Optional[Dict[str, int]] = None
    debt_minimum_payments: Optional[Dict[str, int]] = None
    debt_escrow_amounts: Optional[Dict[str, int]] = None
    deleted: bool = Field(
        ...,
        description='Whether or not the account has been deleted.  Deleted accounts will only be included in delta requests.',
    )

class Category(BaseModel):
    id: UUID
    category_group_id: UUID
    category_group_name: Optional[str] = None
    name: str
    hidden: bool = Field(..., description='Whether or not the category is hidden')
    original_category_group_id: Optional[UUID] = None
    note: Optional[str] = None
    budgeted: int = Field(..., description='Budgeted amount in milliunits format')
    activity: int = Field(..., description='Activity amount in milliunits format')
    balance: int = Field(..., description='Balance in milliunits format')
    goal_type: Optional[GoalTypeEnum] = Field(
        None,
        description="The type of goal, if the category has a goal (TB='Target Category Balance', TBD='Target Category Balance by Date', MF='Monthly Funding', NEED='Plan Your Spending')",
    )
    goal_day: Optional[int] = Field(
        None,
        description="A day offset modifier for the goal's due date. When goal_cadence is 2 (Weekly), this value specifies which day of the week the goal is due (0 = Sunday, 6 = Saturday). Otherwise, this value specifies which day of the month the goal is due (1 = 1st, 31 = 31st, null = Last day of Month).",
    )
    goal_cadence: Optional[int] = Field(
        None,
        description="The goal cadence. Value in range 0-14. There are two subsets of these values which behave differently. For values 0, 1, 2, and 13, the goal's due date repeats every goal_cadence * goal_cadence_frequency, where 0 = None, 1 = Monthly, 2 = Weekly, and 13 = Yearly. For example, goal_cadence 1 with goal_cadence_frequency 2 means the goal is due every other month. For values 3-12 and 14, goal_cadence_frequency is ignored and the goal's due date repeats every goal_cadence, where 3 = Every 2 Months, 4 = Every 3 Months, ..., 12 = Every 11 Months, and 14 = Every 2 Years.",
    )
    goal_cadence_frequency: Optional[int] = Field(
        None,
        description="The goal cadence frequency. When goal_cadence is 0, 1, 2, or 13, a goal's due date repeats every goal_cadence * goal_cadence_frequency. For example, goal_cadence 1 with goal_cadence_frequency 2 means the goal is due every other month.  When goal_cadence is 3-12 or 14, goal_cadence_frequency is ignored.",
    )
    goal_creation_month: Optional[str] = Field(
        None, description='The month a goal was created'
    )
    goal_target: Optional[int] = Field(
        None, description='The goal target amount in milliunits'
    )
    goal_target_month: Optional[str] = Field(
        None,
        description='The original target month for the goal to be completed.  Only some goal types specify this date.',
    )
    goal_percentage_complete: Optional[int] = Field(
        None, description='The percentage completion of the goal'
    )
    goal_months_to_budget: Optional[int] = Field(
        None,
        description='The number of months, including the current month, left in the current goal period.',
    )
    goal_under_funded: Optional[int] = Field(
        None,
        description="The amount of funding still needed in the current month to stay on track towards completing the goal within the current goal period. This amount will generally correspond to the 'Underfunded' amount in the web and mobile clients except when viewing a category with a Needed for Spending Goal in a future month.  The web and mobile clients will ignore any funding from a prior goal period when viewing category with a Needed for Spending Goal in a future month.",
    )
    goal_overall_funded: Optional[int] = Field(
        None,
        description='The total amount funded towards the goal within the current goal period.',
    )
    goal_overall_left: Optional[int] = Field(
        None,
        description='The amount of funding still needed to complete the goal within the current goal period.',
    )
    deleted: bool = Field(
        ...,
        description='Whether or not the category has been deleted.  Deleted categories will only be included in delta requests.',
    )

class CategoryGroupWithCategories(CategoryGroup):
    categories: List[Category] = Field(
        ...,
        description='Category group categories.  Amounts (budgeted, activity, balance, etc.) are specific to the current budget month (UTC).',
    )

# class Data8(BaseModel):
#     category: Category
#     server_knowledge: int = Field(..., description='The knowledge of the server')

class Payee(BaseModel):
    id: UUID
    name: str
    transfer_account_id: Optional[str] = Field(
        None,
        description='If a transfer payee, the `account_id` to which this payee transfers to',
    )
    deleted: bool = Field(
        ...,
        description='Whether or not the payee has been deleted.  Deleted payees will only be included in delta requests.',
    )

# class PayeeLocation(BaseModel):
#     id: UUID
#     payee_id: UUID
#     latitude: str
#     longitude: str
#     deleted: bool = Field(
#         ...,
#         description='Whether or not the payee location has been deleted.  Deleted payee locations will only be included in delta requests.',
#     )

class DebtTransactionTypeEnum(Enum):
    payment = 'payment'
    refund = 'refund'
    fee = 'fee'
    interest = 'interest'
    escrow = 'escrow'
    balanceAdjustment = 'balanceAdjustment'
    credit = 'credit'
    charge = 'charge'

# class Type(Enum):
#     transaction = 'transaction'
#     subtransaction = 'subtransaction'

class SubTransaction(BaseModel):
    id: str
    transaction_id: str
    amount: int = Field(
        ..., description='The subtransaction amount in milliunits format'
    )
    memo: Optional[str] = None
    payee_id: Optional[UUID] = None
    payee_name: Optional[str] = None
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    transfer_account_id: Optional[UUID] = Field(
        None,
        description='If a transfer, the account_id which the subtransaction transfers to',
    )
    transfer_transaction_id: Optional[str] = Field(
        None,
        description='If a transfer, the id of transaction on the other side of the transfer',
    )
    deleted: bool = Field(
        ...,
        description='Whether or not the subtransaction has been deleted.  Deleted subtransactions will only be included in delta requests.',
    )

class Frequency(Enum):
    never = 'never'
    daily = 'daily'
    weekly = 'weekly'
    everyOtherWeek = 'everyOtherWeek'
    twiceAMonth = 'twiceAMonth'
    every4Weeks = 'every4Weeks'
    monthly = 'monthly'
    everyOtherMonth = 'everyOtherMonth'
    every3Months = 'every3Months'
    every4Months = 'every4Months'
    twiceAYear = 'twiceAYear'
    yearly = 'yearly'
    everyOtherYear = 'everyOtherYear'

class ScheduledSubTransaction(BaseModel):
    id: UUID
    scheduled_transaction_id: UUID
    amount: int = Field(
        ..., description='The scheduled subtransaction amount in milliunits format'
    )
    memo: Optional[str] = None
    payee_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    transfer_account_id: Optional[UUID] = Field(
        None,
        description='If a transfer, the account_id which the scheduled subtransaction transfers to',
    )
    deleted: bool = Field(
        ...,
        description='Whether or not the scheduled subtransaction has been deleted. Deleted scheduled subtransactions will only be included in delta requests.',
    )

# class MonthSummary(BaseModel):
#     month: str
#     note: Optional[str] = None
#     income: int = Field(
#         ...,
#         description="The total amount of transactions categorized to 'Inflow: Ready to Assign' in the month",
#     )
#     budgeted: int = Field(..., description='The total amount budgeted in the month')
#     activity: int = Field(
#         ...,
#         description="The total amount of transactions in the month, excluding those categorized to 'Inflow: Ready to Assign'",
#     )
#     to_be_budgeted: int = Field(
#         ..., description="The available amount for 'Ready to Assign'"
#     )
#     age_of_money: Optional[int] = Field(
#         None, description='The Age of Money as of the month'
#     )
#     deleted: bool = Field(
#         ...,
#         description='Whether or not the month has been deleted.  Deleted months will only be included in delta requests.',
#     )

# class MonthDetail(MonthSummary):
#     categories: List[Category] = Field(
#         ...,
#         description='The budget month categories.  Amounts (budgeted, activity, balance, etc.) are specific to the {month} parameter specified.',
#     )

class TransactionFlagColorEnum(Enum):
    red = 'red'
    orange = 'orange'
    yellow = 'yellow'
    green = 'green'
    blue = 'blue'
    purple = 'purple'

class TransactionClearedStatus(Enum):
    cleared = 'cleared'
    uncleared = 'uncleared'
    reconciled = 'reconciled'

# class Data7(BaseModel):
#     category: Category

# class CategoryResponse(BaseModel):
#     data: Data7


class Data9(BaseModel):
    payees: List[Payee]
    server_knowledge: int = Field(..., description='The knowledge of the server')

class PayeesResponse(BaseModel):
    data: Data9

# class Data10(BaseModel):
#     payee: Payee

# class PayeeResponse(BaseModel):
#     data: Data10

class TransactionSummary(BaseModel):
    id: str
    date: str = Field(
        ..., description='The transaction date in ISO format (e.g. 2016-12-01)'
    )
    amount: int = Field(..., description='The transaction amount in milliunits format')
    memo: Optional[str] = None
    cleared: TransactionClearedStatus
    approved: bool = Field(
        ..., description='Whether or not the transaction is approved'
    )
    flag_color: Optional[TransactionFlagColorEnum] = None
    account_id: UUID
    payee_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    transfer_account_id: Optional[UUID] = Field(
        None, description='If a transfer transaction, the account to which it transfers'
    )
    transfer_transaction_id: Optional[str] = Field(
        None,
        description='If a transfer transaction, the id of transaction on the other side of the transfer',
    )
    matched_transaction_id: Optional[str] = Field(
        None, description='If transaction is matched, the id of the matched transaction'
    )
    import_id: Optional[str] = Field(
        None,
        description="If the transaction was imported, this field is a unique (by account) import identifier.  If this transaction was imported through File Based Import or Direct Import and not through the API, the import_id will have the format: 'YNAB:[milliunit_amount]:[iso_date]:[occurrence]'.  For example, a transaction dated 2015-12-30 in the amount of -$294.23 USD would have an import_id of 'YNAB:-294230:2015-12-30:1'.  If a second transaction on the same account was imported and had the same date and same amount, its import_id would be 'YNAB:-294230:2015-12-30:2'.",
    )
    import_payee_name: Optional[str] = Field(
        None,
        description='If the transaction was imported, the payee name that was used when importing and before applying any payee rename rules',
    )
    import_payee_name_original: Optional[str] = Field(
        None,
        description='If the transaction was imported, the original payee name as it appeared on the statement',
    )
    debt_transaction_type: Optional[DebtTransactionTypeEnum] = Field(
        None,
        description='If the transaction is a debt/loan account transaction, the type of transaction',
    )
    deleted: bool = Field(
        ...,
        description='Whether or not the transaction has been deleted.  Deleted transactions will only be included in delta requests.',
    )

class TransactionDetail(TransactionSummary):
    account_name: str
    payee_name: Optional[str] = None
    category_name: Optional[str] = Field(
        None,
        description="The name of the category.  If a split transaction, this will be 'Split'.",
    )
    subtransactions: List[SubTransaction] = Field(
        ..., description='If a split transaction, the subtransactions.'
    )

# class HybridTransaction(TransactionSummary):
#     type: Type = Field(
#         ...,
#         description='Whether the hybrid transaction represents a regular transaction or a subtransaction',
#     )
#     parent_transaction_id: Optional[str] = Field(
#         None,
#         description='For subtransaction types, this is the id of the parent transaction.  For transaction types, this id will be always be null.',
#     )
#     account_name: str
#     payee_name: Optional[str] = None
#     category_name: Optional[str] = Field(
#         None,
#         description="The name of the category.  If a split transaction, this will be 'Split'.",
#     )

class ScheduledTransactionSummary(BaseModel):
    id: UUID
    date_first: str = Field(
        ...,
        description='The first date for which the Scheduled Transaction was scheduled.',
    )
    date_next: str = Field(
        ...,
        description='The next date for which the Scheduled Transaction is scheduled.',
    )
    frequency: Frequency
    amount: int = Field(
        ..., description='The scheduled transaction amount in milliunits format'
    )
    memo: Optional[str] = None
    flag_color: Optional[TransactionFlagColorEnum] = None
    account_id: UUID
    payee_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    transfer_account_id: Optional[UUID] = Field(
        None,
        description='If a transfer, the account_id which the scheduled transaction transfers to',
    )
    deleted: bool = Field(
        ...,
        description='Whether or not the scheduled transaction has been deleted.  Deleted scheduled transactions will only be included in delta requests.',
    )

class ScheduledTransactionDetail(ScheduledTransactionSummary):
    account_name: str
    payee_name: Optional[str] = None
    category_name: Optional[str] = Field(
        None,
        description="The name of the category.  If a split scheduled transaction, this will be 'Split'.",
    )
    subtransactions: List[ScheduledSubTransaction] = Field(
        ..., description='If a split scheduled transaction, the subtransactions.'
    )

# class Data21(BaseModel):
#     months: List[MonthSummary]
#     server_knowledge: int = Field(..., description='The knowledge of the server')

# class MonthSummariesResponse(BaseModel):
#     data: Data21

# class Data22(BaseModel):
#     month: MonthDetail

# class MonthDetailResponse(BaseModel):
#     data: Data22

# class BudgetSummary(BaseModel):
#     id: UUID
#     name: str
#     last_modified_on: Optional[str] = Field(
#         None,
#         description='The last time any changes were made to the budget from either a web or mobile client',
#     )
#     first_month: Optional[str] = Field(None, description='The earliest budget month')
#     last_month: Optional[str] = Field(None, description='The latest budget month')
#     date_format: Optional[str] = None
#     currency_format: Optional[CurrencyFormat] = None
#     accounts: Optional[List[Account]] = Field(
#         None,
#         description='The budget accounts (only included if `include_accounts=true` specified as query parameter)',
#     )

# class BudgetDetail(BudgetSummary):
#     accounts: Optional[List[Account]] = None
#     payees: Optional[List[Payee]] = None
#     payee_locations: Optional[List[PayeeLocation]] = None
#     category_groups: Optional[List[CategoryGroup]] = None
#     categories: Optional[List[Category]] = None
#     months: Optional[List[MonthDetail]] = None
#     transactions: Optional[List[TransactionSummary]] = None
#     subtransactions: Optional[List[SubTransaction]] = None
#     scheduled_transactions: Optional[List[ScheduledTransactionSummary]] = None
#     scheduled_subtransactions: Optional[List[ScheduledSubTransaction]] = None

class Data13(BaseModel):
    transactions: List[TransactionDetail]
    server_knowledge: int = Field(..., description='The knowledge of the server')

class TransactionsResponse(BaseModel):
    data: Data13

# class Data16(BaseModel):
#     transaction: TransactionDetail

# class TransactionResponse(BaseModel):
#     data: Data16

class Data19(BaseModel):
    scheduled_transactions: List[ScheduledTransactionDetail]
    server_knowledge: int = Field(..., description='The knowledge of the server')

class ScheduledTransactionsResponse(BaseModel):
    data: Data19

# class Data20(BaseModel):
#     scheduled_transaction: ScheduledTransactionDetail

# class ScheduledTransactionResponse(BaseModel):
#     data: Data20

# class Data1(BaseModel):
#     budgets: List[BudgetSummary]
#     default_budget: Optional[BudgetSummary] = None

# class BudgetSummaryResponse(BaseModel):
#     data: Data1

class Data4(BaseModel):
    accounts: List[Account]
    server_knowledge: int = Field(..., description='The knowledge of the server')

class AccountsResponse(BaseModel):
    data: Data4

class Data5(BaseModel):
    account: Account

class AccountResponse(BaseModel):
    data: Data5

class Data6(BaseModel):
    category_groups: List[CategoryGroupWithCategories]
    server_knowledge: int = Field(..., description='The knowledge of the server')

class CategoriesResponse(BaseModel):
    data: Data6
