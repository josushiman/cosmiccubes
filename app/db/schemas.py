import logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(filename)s %(asctime)s %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

from tortoise import Tortoise
from tortoise.contrib.pydantic import pydantic_model_creator
logging.info("Initialising Models")
Tortoise.init_models(["app.db.models"], "models")

from .models import YnabAccounts, YnabCategories, YnabMonthSummaries, YnabPayees, \
    YnabServerKnowledge, YnabTransactions, Budgets, Savings

# Accounts_Pydantic = pydantic_model_creator(Accounts, name="Accounts")
# AccountTypes_Pydantic = pydantic_model_creator(AccountTypes, name="AccountTypes", exclude="accounts")
# BalanceTransfers_Pydantic = pydantic_model_creator(BalanceTransfers, name="BalanceTransfers")
Budgets_Pydantic = pydantic_model_creator(Budgets, name="Budgets")
# Companies_Pydantic = pydantic_model_creator(Companies, name="Companies")
# CompanyCategories_Pydantic = pydantic_model_creator(CompanyCategories, name="CompanyCategories")
# DirectDebits_Pydantic = pydantic_model_creator(DirectDebits, name="DirectDebits")
# Incomes_Pydantic = pydantic_model_creator(Incomes, name="Incomes")
# Mortgages_Pydantic = pydantic_model_creator(Mortgages, name="Mortgages")
# Projects_Pydantic = pydantic_model_creator(Projects, name="Projects")
# ProjectItems_Pydantic = pydantic_model_creator(ProjectItems, name="ProjectItems")
Savings_Pydantic = pydantic_model_creator(Savings, name="Savings")
YnabAccounts_Pydantic = pydantic_model_creator(YnabAccounts, name="YnabAccounts")
YnabCategories_Pydantic = pydantic_model_creator(YnabCategories, name="YnabCategories")
YnabMonthSummaries_Pydantic = pydantic_model_creator(YnabMonthSummaries, name="YnabMonthSummaries")
YnabPayees_Pydantic = pydantic_model_creator(YnabPayees, name="YnabPayees")
YnabServerKnowledge_Pydantic = pydantic_model_creator(YnabServerKnowledge, name="YnabServerKnowledge")
YnabTransactions_Pydantic = pydantic_model_creator(YnabTransactions, name="YnabTransactions")
