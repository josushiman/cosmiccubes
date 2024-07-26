import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(filename)s %(asctime)s %(message)s",
    handlers=[logging.StreamHandler()],
)

from tortoise import Tortoise
from tortoise.contrib.pydantic import pydantic_model_creator

logging.info("Initialising Models")
Tortoise.init_models(["app.db.models"], "models")

from .models import (
    YnabAccounts,
    YnabCategories,
    YnabMonthSummaries,
    YnabPayees,
    YnabServerKnowledge,
    YnabTransactions,
    Budgets,
    CardPayments,
    HeartRates,
    Savings,
    LoansAndRenewals,
    LoansAndRenewalsPeriods,
    LoansAndRenewalsTypes,
    Workouts,
    WorkoutTypes,
)

Budgets_Pydantic = pydantic_model_creator(Budgets, name="Budgets")
CardPayments_Pydantic = pydantic_model_creator(CardPayments, name="Card Payments")
LoansAndRenewals_Pydantic = pydantic_model_creator(
    LoansAndRenewals, name="LoansAndRenewals"
)
LoansAndRenewalsPeriods_Pydantic = pydantic_model_creator(
    LoansAndRenewalsPeriods, name="LoansAndRenewalsPeriods"
)
LoansAndRenewalsTypes_Pydantic = pydantic_model_creator(
    LoansAndRenewalsTypes, name="LoansAndRenewalsTypes"
)
HeartRates_Pydantic = pydantic_model_creator(HeartRates, name="HeartRates")
Savings_Pydantic = pydantic_model_creator(Savings, name="Savings")
Workouts_Pydantic = pydantic_model_creator(Workouts, name="Workouts")
WorkoutTypes_Pydantic = pydantic_model_creator(WorkoutTypes, name="WorkoutTypes")
YnabAccounts_Pydantic = pydantic_model_creator(YnabAccounts, name="YnabAccounts")
YnabCategories_Pydantic = pydantic_model_creator(YnabCategories, name="YnabCategories")
YnabMonthSummaries_Pydantic = pydantic_model_creator(
    YnabMonthSummaries, name="YnabMonthSummaries"
)
YnabPayees_Pydantic = pydantic_model_creator(YnabPayees, name="YnabPayees")
YnabServerKnowledge_Pydantic = pydantic_model_creator(
    YnabServerKnowledge, name="YnabServerKnowledge"
)
YnabTransactions_Pydantic = pydantic_model_creator(
    YnabTransactions, name="YnabTransactions"
)
