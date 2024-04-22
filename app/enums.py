from enum import Enum, IntEnum

class LoansAndRenewalsEnum(Enum):
    INSRUANCE = 'insurance'
    SUBSCRIPTION = 'subscription'
    LOAN = 'loan'

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
