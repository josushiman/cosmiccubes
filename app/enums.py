from enum import Enum, IntEnum

class FilterTypes(Enum):
    ACCOUNT = 'account'
    CATEGORY = 'category'
    PAYEE = 'payee'

class PeriodOptions(Enum):
    TODAY = 'TODAY'
    YESTERDAY = 'YESTERDAY'
    THIS_WEEK = 'THIS_WEEK'
    LAST_WEEK = 'LAST_WEEK'

class PeriodMonthOptions(IntEnum):
    MONTHS_1 = 1
    MONTHS_3 = 3
    MONthS_6 = 6
    MONTHS_9 = 9
    MONTHS_12 = 12

class SpecificMonthOptions(Enum):
    JANUARY = '01'
    FEBRUARY = '02'
    MARCH = '03'
    APRIL = '04'
    MAY = '05'
    JUNE = '06'
    JULY = '07'
    AUGUST = '08'
    SEPTEMBER = '09'
    OCTOBER = '10'
    NOVEMBER = '11'
    DECEMBER = '12'

class SpecificYearOptions(Enum):
    YEAR_23 = '2023'
    YEAR_24 = '2024'
    YEAR_25 = '2025'

class TopXOptions(IntEnum):
    TOP_3 = 3
    TOP_5 = 5
    TOP_10 = 10

class TransactionTypeOptions(Enum):
    INCOME = 'income'
    EXPENSES = 'expenses'