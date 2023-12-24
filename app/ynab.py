import os
import requests
import logging
import json
from dotenv import load_dotenv
from app.ynab_models import AccountsResponse, CategoriesResponse
from fastapi import HTTPException

load_dotenv()
dotenv_ynab_url = os.getenv("EXT_YNAB_URL")
dotenv_ynab_token = os.getenv("EXT_YNAB_TOKEN")

class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token
    def __call__(self, r):
        r.headers["authorization"] = "Bearer " + self.token
        return r

class YNAB():
    @classmethod
    async def convert_to_float(cls, amount):
        # Amount comes in as a milliunit e.g. 21983290
        # It needs to be returned as 21983.29
        return amount / 1000

    @classmethod
    async def convert_to_pydantic(cls, action: str, _dict: dict):
        pydantic_class = await cls.get_class(action)
        return pydantic_class.model_validate_json(json.dumps(_dict))

    @classmethod
    async def get_class(cls, action: str):
        class_list ={
            "accounts-list": AccountsResponse,
            "categories-list": CategoriesResponse,
        }

        try:
            return class_list[action]
        except KeyError:
            logging.warning(f"Class for {action} doesn't exist.")
            raise HTTPException(status_code=400)

    @classmethod
    async def get_route(cls, action: str, param_1: str = None, param_2: str = None, since_date: str = None, month: str = None) -> str:
        '''
        Get the route of the YNAB endpoint you want to call. Passed as a string, returned as a string.
        action = a friendly string of the action needed to be made
        param_1 = budget_id
        param_2 = the section your are calling id (e.g. account_id, or category_id)
        since_date = used for the transactions-list route to get transactions since a specific date. provided in ISO format (e.g. 2016-12-01)
        month = only used when getting categories for a single month. provided in ISO format (e.g. 2016-12-01)

        Source: https://api.ynab.com/v1
        Rate limit: 200 requests per hour
        '''
        match action:
            case 'accounts-list':
                # Returns all accounts
                return f'/budgets/{param_1}/accounts'
            
            case 'accounts-single':
                # Returns a single account
                return f'/budgets/{param_1}/accounts/{param_2}'
            
            case 'budgets-list':
                # Returns budgets list with summary information
                return '/budgets'
            
            case 'budgets-single':
                # Returns a single budget with all related entities. This resource is effectively a full budget export.
                return f'/budgets/{param_1}'
            
            case 'categories-list':
                # Returns all categories grouped by category group. 
                # Amounts (budgeted, activity, balance, etc.) are specific to the current budget month (UTC).
                return f'/budgets/{param_1}/categories'
            
            case 'categories-single':
                # Returns a single category. Amounts (budgeted, activity, balance, etc.) are specific to the current budget month (UTC).
                return f'/budgets/{param_1}/categories/{param_2}'
            
            case 'categories-single-month':
                # Returns a single category for a specific budget month. 
                # Amounts (budgeted, activity, balance, etc.) are specific to the current budget month (UTC).
                # month -> The budget month in ISO format (e.g. 2016-12-01)
                return f'/budgets/{param_1}/months/{month}/categories/{param_2}'
            
            case 'months-list':
                # Returns all budget months
                return f'/budgets/{param_1}/months'
            
            case 'months-single':
                # Returns all budget months
                return f'/budgets/{param_1}/months/{month}'
            
            case 'payees-list':
                # Returns all payees/merchants
                return f'/budgets/{param_1}/payees'
            
            case 'schedule-transactions-list':
                # Returns all scheduled transactions
                return f'/budgets/{param_1}/scheduled_transactions'
            
            case 'schedule-transactions-single':
                # Returns a single scheduled transaction
                return f'/budgets/{param_1}/scheduled_transactions/{param_2}'
            
            case 'transactions-list':
                # Returns budget transactions
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/transactions'
                return f'/budgets/{param_1}/transactions?since_date={since_date}'
            
            case 'transactions-single':
                # Returns a single transaction
                return f'/budgets/{param_1}/transactions/{param_2}'
            
            case 'transactions-list-account':
                # Returns all transactions for a specified account
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/accounts/{param_2}/transactions'
                return f'/budgets/{param_1}/accounts/{param_2}/transactions?since_date={since_date}'
            
            case 'transactions-list-category':
                # Returns all transactions for a specified category
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/categories/{param_2}/transactions'
                return f'/budgets/{param_1}/categories/{param_2}/transactions?since_date={since_date}'
            
            case 'transactions-list-payee':
                # Returns all transactions for a specified payee
                # since_date -> If specified, only transactions on or after this date will be included. (e.g. 2016-12-01)
                if not since_date: return f'/budgets/{param_1}/payees/{param_2}/transactions'
                return f'/budgets/{param_1}/payees/{param_2}/transactions?since_date={since_date}'
            
            case _:
                return '/user'
    
    @classmethod
    async def make_request(cls, action: str, param_1: str = None, param_2: str = None, since_date: str = None, month: str = None):
        ynab_route = await cls.get_route(action, param_1, param_2, since_date, month)
        ynab_url = dotenv_ynab_url + ynab_route

        logging.debug(f'Attempting to call YNAB with {ynab_url}')

        try:
            response = requests.get(ynab_url, auth=BearerAuth(dotenv_ynab_token))
        except Exception as exc:
            logging.error(exc)

        return response.json()

    @classmethod
    async def get_balance_info(cls):
        account_list = await cls.make_request('accounts-list', param_1='25c0c5c4-98fa-452c-9d31-ee3eaa50e1b2') #TODO
        pydantic_accounts_list = await cls.convert_to_pydantic('accounts-list', account_list)

        total_amount = 0.00
        spent_amount = 0.00

        for account in pydantic_accounts_list.data.accounts:
            if account.type.value == 'checking':
                total_amount += account.balance
            else:
                spent_amount += account.balance

            logging.debug(f'''
            name: {account.name}
            balance: {account.balance}
            cleared: {account.cleared_balance}
            uncleared: {account.uncleared_balance}
            ''')

        # Units are returned as milliunits.
        available_amount = await cls.convert_to_float(total_amount -- spent_amount)
        total_amount = await cls.convert_to_float(total_amount)
        spent_amount = await cls.convert_to_float(spent_amount)

        return {
            "total": total_amount,
            "spent": spent_amount,
            "available": available_amount,
        }
    
    @classmethod
    async def get_category_summary(cls):
        category_list = await cls.make_request('categories-list', param_1='25c0c5c4-98fa-452c-9d31-ee3eaa50e1b2') #TODO
        pydantic_categories_list = await cls.convert_to_pydantic('categories-list', category_list)

        result_json = []

        for category_group in pydantic_categories_list.data.category_groups:
            count_categories = len(category_group.categories)
            if count_categories < 1: continue

            total_balance = 0.0
            total_budgeted = 0.0
            total_goal = 0
            for category in category_group.categories:
                total_balance += category.balance
                total_budgeted += category.budgeted
                if category.goal_percentage_complete:
                    total_goal += category.goal_percentage_complete
            
            if category_group.name != 'Credit Card Payments':
                total_goal = total_goal / count_categories

            result_json.append({
                'name': category_group.name,
                'available': await cls.convert_to_float(total_balance),
                'budgeted': await cls.convert_to_float(total_budgeted),
                'goal': total_goal,
            })
        
        return result_json

    # Get last X transactions
    # Get next X scheduled transactions
        # Filter out any transactions which do not have an import_id
    
    
    # Total Spent current month
    # Income, by month
    # Expenses, by month

    # 
    
    # All time
    # By month
    # ---
    # Total expenses by category
    # Total expenses by account
    # Total expenses by payee
    # Top 5 expenses by category
    # Top 5 expenses by payee

    # Last paid date for account/credit cards
