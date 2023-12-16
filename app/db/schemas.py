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

from .models import Accounts, AccountTypes, BalanceTransfers, Budgets, Companies, CompanyCategories, DirectDebits, Incomes, \
    Mortgages, Projects, ProjectItems, ProjectItemCategories, Transactions

Accounts_Pydantic = pydantic_model_creator(Accounts, name="Accounts")
AccountTypes_Pydantic = pydantic_model_creator(AccountTypes, name="AccountTypes", exclude="accounts")
BalanceTransfers_Pydantic = pydantic_model_creator(BalanceTransfers, name="BalanceTransfers")
Budgets_Pydantic = pydantic_model_creator(Budgets, name="Budgets")
Companies_Pydantic = pydantic_model_creator(Companies, name="Companies")
CompanyCategories_Pydantic = pydantic_model_creator(CompanyCategories, name="CompanyCategories")
DirectDebits_Pydantic = pydantic_model_creator(DirectDebits, name="DirectDebits")
Incomes_Pydantic = pydantic_model_creator(Incomes, name="Incomes")
Mortgages_Pydantic = pydantic_model_creator(Mortgages, name="Mortgages")
Projects_Pydantic = pydantic_model_creator(Projects, name="Projects")
ProjectItems_Pydantic = pydantic_model_creator(ProjectItems, name="ProjectItems")
ProjectItemCategories_Pydantic = pydantic_model_creator(ProjectItemCategories, name="ProjectItemCategories")
Transactions_Pydantic = pydantic_model_creator(Transactions, name="Transactions")
