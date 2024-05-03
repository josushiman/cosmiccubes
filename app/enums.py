from enum import Enum, IntEnum


class LoansAndRenewalsEnum(Enum):
    INSRUANCE = "insurance"
    SUBSCRIPTION = "subscription"
    LOAN = "loan"


class PeriodMonthOptionsIntEnum(IntEnum):
    MONTHS_1 = 1
    MONTHS_3 = 3
    MONthS_6 = 6
    MONTHS_9 = 9
    MONTHS_12 = 12


class SpecificMonthOptionsEnum(IntEnum):
    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12


class SpecificYearOptionsEnum(IntEnum):
    YEAR_24 = 2024
    YEAR_25 = 2025
