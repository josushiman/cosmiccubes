import os
import httpx
import logging
import json
from enum import Enum, IntEnum
from time import localtime, mktime
from datetime import datetime
from pandas import DateOffset
from async_lru import alru_cache
from dotenv import load_dotenv
from app.ynab_models import AccountsResponse, CategoriesResponse, PayeesResponse, TransactionsResponse
from fastapi import HTTPException

load_dotenv()
dotenv_ynab_url = os.getenv("EXT_YNAB_URL")
dotenv_ynab_token = os.getenv("EXT_YNAB_TOKEN")
dotenv_ynab_budget_id = os.getenv("YNAB_BUDGET_ID")

class YNAB():
    @classmethod
    async def convert_to_float(cls, amount):
        # Amount comes in as a milliunit e.g. 21983290
        # It needs to be returned as 21983.29
        return amount / 1000

    @classmethod
    async def get_date_for_transactions(cls, year: str = None, months: int = None, specific_month: str = None):
        if year and not specific_month:
            logging.debug("Getting transactions for the current year.")
            return f'{year.value}-01-01'
        
        if months:
            logging.debug(f"Getting transactions for the last {months.value} months.")
            current_month = datetime.today() - DateOffset(months=months)
            return current_month.strftime('%Y-%m') + '-01'
        
        if specific_month and year:
            logging.debug(f"Getting transactions for {year.value}-{specific_month.value}-01.")
            return f'{year.value}-{specific_month.value}-01'
        
        if specific_month:
            current_year = datetime.today().strftime('%Y')
            logging.debug(f"Getting transactions for {current_year}-{specific_month.value}-01.")
            return f'{current_year}-{specific_month.value}-01'
        
        logging.debug("Getting transactions for this month only.")
        return datetime.today().strftime('%Y-%m') + '-01'

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
                if param_2: return f'/budgets/{param_1}/transactions?server_knowledge={param_2}'
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
    
    # TODO only use this if i don't have the transaction stored on the pi.
    @classmethod
    @alru_cache(maxsize=32) # Caches requests so we don't overuse them.
    async def make_request(cls, action: str, param_1: str = None, param_2: str = None, since_date: str = None, month: str = None):
        ynab_route = await cls.get_route(action, param_1, param_2, since_date, month)
        ynab_url = dotenv_ynab_url + ynab_route

        logging.debug(f'Attempting to call YNAB with {ynab_url}')

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(ynab_url, headers={'Authorization': f"Bearer {dotenv_ynab_token}"})
                return response.json()
            except httpx.HTTPError as exc:
                logging.debug(exc)
                raise HTTPException(status_code=500)

    @classmethod
    async def get_available_balance(cls):
        account_list = await cls.make_request('accounts-list', param_1=dotenv_ynab_budget_id)
        pydantic_accounts_list = AccountsResponse.model_validate_json(json.dumps(account_list))

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
    async def get_card_balances(cls):
        account_list = await cls.make_request('accounts-list', param_1=dotenv_ynab_budget_id)
        pydantic_accounts_list = AccountsResponse.model_validate_json(json.dumps(account_list))


        result_json = {
            "data": []
        }

        for account in pydantic_accounts_list.data.accounts:
            if account.type.value == 'checking': continue
            
            result_json["data"].append({
                "name": account.name,
                "balance": await cls.convert_to_float(account.balance),
                "cleared": await cls.convert_to_float(account.cleared_balance),
                "uncleared": await cls.convert_to_float(account.uncleared_balance),
            })

            logging.debug(f'''
            name: {account.name}
            balance: {account.balance}
            cleared: {account.cleared_balance}
            uncleared: {account.uncleared_balance}
            ''')

        return result_json

    @classmethod
    async def get_category_summary(cls):
        category_list = await cls.make_request('categories-list', param_1=dotenv_ynab_budget_id)
        pydantic_categories_list = CategoriesResponse.model_validate_json(json.dumps(category_list))

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
            
            # Skip all the categories that have no budget associated to them.
            if total_budgeted == 0.0: continue

            if category_group.name != 'Credit Card Payments':
                total_goal = total_goal / count_categories

            result_json.append({
                'name': category_group.name,
                'available': await cls.convert_to_float(total_balance),
                'budgeted': await cls.convert_to_float(total_budgeted),
                'goal': total_goal,
            })
        
        # Show the categories with the higher goals first.
        sorted_list = sorted(result_json, key=lambda obj: obj['goal'], reverse=True)

        return sorted_list

    @classmethod
    async def get_last_x_transactions(cls, count: int, since_date: str = None):
        # For now just get all the transactions, but need to figure out a better way to get the latest results using the since_date.
        transaction_list = await cls.make_request('transactions-list', param_1=dotenv_ynab_budget_id)
        pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))

        all_results = []

        for transaction in pydantic_transactions_list.data.transactions:
            all_results.append(transaction.model_dump())

        result_json = sorted(all_results, key=lambda item: item['date'], reverse=True)
        
        return result_json[0:count]
    
    @classmethod
    async def get_totals(cls, filter_type: Enum, year: Enum = None, months: IntEnum = None, specific_month: Enum = None, \
        transaction_type: Enum = None):
        
        transactions = await cls.transactions_by_filter_type(
            filter_type=filter_type,
            year=year,
            months=months,
            specific_month=specific_month,
            transaction_type=transaction_type
        )
        
        total_spent = 0.0

        for account in transactions['data']:
            total_spent += account['total']

        return {
            'since_date': transactions['since_date'],
            'total': total_spent
        }
    
    @classmethod
    async def transactions_by_filter_type(cls, filter_type: Enum, year: Enum = None, months: IntEnum = None, specific_month: Enum = None, \
        top_x: IntEnum = None, transaction_type: Enum = None):

        entities_raw = {}
        match filter_type.value:
            case 'account':
                logging.debug("Getting accounts list.")
                account_list = await cls.make_request('accounts-list', param_1=dotenv_ynab_budget_id)
                pydantic_categories_list = AccountsResponse.model_validate_json(json.dumps(account_list))
                for account in pydantic_categories_list.data.accounts:
                    entities_raw[f'{account.id}'] = {
                        'id': account.id,
                        'name': account.name,
                        'total': 0
                    }
            case 'payee':
                logging.debug("Getting payees list.")
                payee_list = await cls.make_request('payees-list', param_1=dotenv_ynab_budget_id)
                pydantic_categories_list = PayeesResponse.model_validate_json(json.dumps(payee_list))
                for payee in pydantic_categories_list.data.payees:
                    entities_raw[f'{payee.id}'] = {
                        'id': payee.id,
                        'name': payee.name,
                        'total': 0
                    }
            case _:
                if filter_type.value != 'category':
                    logging.warn(f"Somehow filter_type was set to something that I can't handle. {filter_type.value}")
                logging.debug("Getting categories list.")
                category_list = await cls.make_request('categories-list', param_1=dotenv_ynab_budget_id)
                pydantic_categories_list = CategoriesResponse.model_validate_json(json.dumps(category_list))
                for category_group in pydantic_categories_list.data.category_groups:
                    for category in category_group.categories:
                        entities_raw[f'{category.id}'] = {
                            'id': category.id,
                            'name': category.name,
                            'category_group_name': category.category_group_name,
                            'category_group_id': category.category_group_id,
                            'total': 0
                        }
        
        since_date = await cls.get_date_for_transactions(year, months, specific_month)
        result_json = {
            'since_date': since_date,
            'data': []
        }

        transaction_list = await cls.make_request('transactions-list', param_1=dotenv_ynab_budget_id, since_date=since_date)
        pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))
        for transaction in pydantic_transactions_list.data.transactions:
            try:
                if filter_type.value == 'account':
                    # don't include transfers/payments
                    if transaction_type.value == 'income' and transaction.amount <= 0 or \
                    transaction_type.value == 'expenses' and transaction.amount >= 0: continue
                    entities_raw[f'{transaction.account_id}']['total'] += transaction.amount
                elif filter_type.value == 'category':
                    entities_raw[f'{transaction.category_id}']['total'] += transaction.amount
                else:
                    entities_raw[f'{transaction.payee_id}']['total'] += transaction.amount
            except KeyError:
                logging.debug(f"Issue with trying to assign transaction amount to uncategorised transaction. {transaction.account_name} - {transaction.payee_name}")
                continue

        all_results = []
        for value in entities_raw.values():
            if transaction_type.value == 'income':
                if value['total'] < 0: continue
            else:
                if value['total'] >= 0: continue
            
            value['total'] = await cls.convert_to_float(value['total'])
            all_results.append(value)

        if transaction_type.value == 'income':
            remove_zero_totals = []
            for value in all_results:
                if value['total'] > 0: remove_zero_totals.append(value)
            result_json['data'] = sorted(remove_zero_totals, key=lambda item: item['total'], reverse=True)
        else:
            result_json['data'] = sorted(all_results, key=lambda item: item['total'])

        if top_x:
            result_json['data'] = result_json['data'][0:top_x]

        return result_json

    @classmethod
    async def transactions_by_month_for_year(cls, year: Enum = None):
        since_date = f'{year.value}-01-01'
        
        january = {
            "month": 1,
            "month_long": "January",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        february = {
            "month": 2,
            "month_long": "February",
            "month_short": "F",
            "total_spent": 0,
            "total_earned": 0
        }
        march = {
            "month": 3,
            "month_long": "March",
            "month_short": "M",
            "total_spent": 0,
            "total_earned": 0
        }
        april = {
            "month": 4,
            "month_long": "April",
            "month_short": "A",
            "total_spent": 0,
            "total_earned": 0
        }
        may = {
            "month": 5,
            "month_long": "May",
            "month_short": "M",
            "total_spent": 0,
            "total_earned": 0
        }
        june = {
            "month": 6,
            "month_long": "June",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        july = {
            "month": 7,
            "month_long": "July",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        august = {
            "month": 8,
            "month_long": "August",
            "month_short": "A",
            "total_spent": 0,
            "total_earned": 0
        }
        september = {
            "month": 9,
            "month_long": "September",
            "month_short": "S",
            "total_spent": 0,
            "total_earned": 0
        }
        october = {
            "month": 10,
            "month_long": "October",
            "month_short": "O",
            "total_spent": 0,
            "total_earned": 0
        }
        november = {
            "month": 11,
            "month_long": "November",
            "month_short": "N",
            "total_spent": 0,
            "total_earned": 0
        }
        december = {
            "month": 12,
            "month_long": "December",
            "month_short": "D",
            "total_spent": 0,
            "total_earned": 0
        }

        result_json = {
            'since_date': since_date,
            'data': [
                january, february, march, april, may, june, july, august, september, october, november, december
            ]
        }

        transaction_list = await cls.make_request('transactions-list', param_1=dotenv_ynab_budget_id, since_date=since_date)
        pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))

        skip_payees = ['Starting Balance', '"Transfer : BA AMEX', 'Transfer : HSBC CC', 'Transfer : Barclays CC', 'Transfer : HSBC ADVANCE']
        
        month_match = {
            '01': january,
            '02': february,
            '03': march,
            '04': april,
            '05': may,
            '06': june,
            '07': july,
            '08': august,
            '09': september,
            '10': october,
            '11': november,
            '12': december
        }

        for transaction in pydantic_transactions_list.data.transactions:
            if transaction.payee_name in skip_payees: continue
            
            transaction_month = transaction.date.split('-')[1]

            if transaction.amount > 0:
                month_match[transaction_month]['total_earned'] += await cls.convert_to_float(transaction.amount)
            else:
                month_match[transaction_month]['total_spent'] += await cls.convert_to_float(transaction.amount)
            
        return result_json

    @classmethod
    async def transactions_by_months(cls, months: IntEnum = None):
        since_date = await cls.get_date_for_transactions(year=None, months=months, specific_month=None)
        now = localtime()
        # Returns a tuple of year, month. e.g. [(2024, 1), (2023, 12), (2023, 11)]
        months_to_get = [localtime(mktime((now.tm_year, now.tm_mon - n, 1, 0, 0, 0, 0, 0, 0)))[:2] for n in range(months.value)]
        # Swap the results round so that the oldest month is the first index.
        months_to_get.reverse()

        january = {
            "month": 1,
            "month_long": "January",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        february = {
            "month": 2,
            "month_long": "February",
            "month_short": "F",
            "total_spent": 0,
            "total_earned": 0
        }
        march = {
            "month": 3,
            "month_long": "March",
            "month_short": "M",
            "total_spent": 0,
            "total_earned": 0
        }
        april = {
            "month": 4,
            "month_long": "April",
            "month_short": "A",
            "total_spent": 0,
            "total_earned": 0
        }
        may = {
            "month": 5,
            "month_long": "May",
            "month_short": "M",
            "total_spent": 0,
            "total_earned": 0
        }
        june = {
            "month": 6,
            "month_long": "June",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        july = {
            "month": 7,
            "month_long": "July",
            "month_short": "J",
            "total_spent": 0,
            "total_earned": 0
        }
        august = {
            "month": 8,
            "month_long": "August",
            "month_short": "A",
            "total_spent": 0,
            "total_earned": 0
        }
        september = {
            "month": 9,
            "month_long": "September",
            "month_short": "S",
            "total_spent": 0,
            "total_earned": 0
        }
        october = {
            "month": 10,
            "month_long": "October",
            "month_short": "O",
            "total_spent": 0,
            "total_earned": 0
        }
        november = {
            "month": 11,
            "month_long": "November",
            "month_short": "N",
            "total_spent": 0,
            "total_earned": 0
        }
        december = {
            "month": 12,
            "month_long": "December",
            "month_short": "D",
            "total_spent": 0,
            "total_earned": 0
        }

        month_list = []
        month_match = {
            '1': january,
            '2': february,
            '3': march,
            '4': april,
            '5': may,
            '6': june,
            '7': july,
            '8': august,
            '9': september,
            '10': october,
            '11': november,
            '12': december
        }

        result_json = {
            'since_date': since_date,
            'data': month_list
        }

        # add the months in order of oldest, the latest to the result_json
        for index, (year, month) in enumerate(months_to_get):
            add_month = month_match[str(month)]
            add_month['year'] = str(year)
            month_list.insert(index, add_month)

        transaction_list = await cls.make_request('transactions-list', param_1=dotenv_ynab_budget_id, since_date=since_date)
        pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))

        skip_payees = ['Starting Balance', '"Transfer : BA AMEX', 'Transfer : HSBC CC', 'Transfer : Barclays CC', 'Transfer : HSBC ADVANCE']
        
        for transaction in pydantic_transactions_list.data.transactions:
            if transaction.payee_name in skip_payees: continue
            
            # Convert payment date from string to date.
            date_format = '%Y-%m-%d'
            transaction_date = datetime.strptime(transaction.date, date_format)
            
            # extract the month, and convert to string.
            transaction_month = str(transaction_date.month)

            if transaction.amount > 0:
                month_match[transaction_month]['total_earned'] += await cls.convert_to_float(transaction.amount)
            else:
                month_match[transaction_month]['total_spent'] += await cls.convert_to_float(transaction.amount)
            
        return result_json
    
    @classmethod
    async def last_paid_date_for_accounts(cls, months: IntEnum):
        # Look over the last month. If no payment, assume the bill has not been paid yet.
        since_date = await cls.get_date_for_transactions(year=None, months=months, specific_month=None)
        transaction_list = await cls.make_request('transactions-list', param_1=dotenv_ynab_budget_id, since_date=since_date)
        pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))


        amex = {
            "id": None,
            "date": None,
            "amount": None,
            "account_name": "BA AMEX"
        }
        barclays = {
            "id": None,
            "date": None,
            "amount": None,
            "account_name": "Barclays CC"
        }
        hsbc = {
            "id": None,
            "date": None,
            "amount": None,
            "account_name": "HSBC CC"
        }

        transfer_payments = [amex, barclays, hsbc]

        account_match = {
            'BA AMEX': amex,
            'Barclays CC': barclays,
            'HSBC CC': hsbc,
        }

        for transaction in pydantic_transactions_list.data.transactions:
            if transaction.payee_name != 'Transfer : HSBC ADVANCE': continue

            account_match[transaction.account_name]['id'] = transaction.id
            account_match[transaction.account_name]['date'] = transaction.date
            account_match[transaction.account_name]['amount'] = await cls.convert_to_float(transaction.amount)

        result_json = {
            'since_date': since_date,
            'data': transfer_payments
        }

        return result_json

    @classmethod
    async def spent_in_period(cls, period: Enum):
        # TODO add filters for whether I want to include bills or just things which do not come from a specific account (e.g. Current Account)
        match period.value:
            case 'TODAY':
                current_date = datetime.today().strftime('%Y-%m-%d')
                transaction_list = await cls.make_request(action='transactions-list', param_1=dotenv_ynab_budget_id, since_date=current_date)
                pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))
                
                total_spent = 0.0
                for transaction in pydantic_transactions_list.data.transactions:
                    if transaction.amount > 0: continue
                    total_spent += transaction.amount
                
                return {
                    "spent": await cls.convert_to_float(total_spent)
                }
            case 'YESTERDAY':
                current_date = datetime.today() - DateOffset(days=1)
                current_date = current_date.strftime('%Y-%m-%d')
                transaction_list = await cls.make_request(action='transactions-list', param_1=dotenv_ynab_budget_id, since_date=current_date)
                pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))
                
                total_spent = 0.0
                for transaction in pydantic_transactions_list.data.transactions:
                    if transaction.amount > 0: continue
                    total_spent += transaction.amount
                
                return {
                    "spent": await cls.convert_to_float(total_spent)
                }
            case 'THIS_WEEK':
                current_date = datetime.today()
                days_to_monday =  current_date.weekday() - 0
                current_date = datetime.today() - DateOffset(days=days_to_monday)
                current_date = current_date.strftime('%Y-%m-%d')
                transaction_list = await cls.make_request(action='transactions-list', param_1=dotenv_ynab_budget_id, since_date=current_date)
                pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))
                
                total_spent = 0.0
                for transaction in pydantic_transactions_list.data.transactions:
                    if transaction.amount > 0 or transaction.category_name in ["Loans", "Monthly Bills", "Credit Card Payments", "Yearly Bills"]: continue
                    total_spent += transaction.amount
                
                return {
                    "spent": await cls.convert_to_float(total_spent)
                }
            case 'LAST_WEEK':
                # TODO
                return None
            case _:
                return None

    @classmethod
    async def spent_vs_budget(cls):
        category_list = await cls.make_request('categories-list', param_1=dotenv_ynab_budget_id)
        pydantic_categories_list = CategoriesResponse.model_validate_json(json.dumps(category_list))

        total_balance = 0.0 # Amount difference between whats been budgeted, and the activity.
        total_budgeted = 0.0 # Budget assigned to the category
        total_spent = 0.0
        category_count = 0
        # Only categories that I care about for tracking the monthly target.
        # This is usually when I only have a budget assigned to a category.
        # So I should skip any category which does not have a budget assigned.
        for category_group in pydantic_categories_list.data.category_groups:
            count_categories = len(category_group.categories)
            if count_categories < 1: continue
            if category_group.name not in ["Frequent", "Giving", "Non-Monthly Expenses"]: continue

            for category in category_group.categories:
                total_spent += category.activity
                total_balance += category.balance
                total_budgeted += category.budgeted
                logging.debug(f'''
                Category details:
                    name: {category.name}
                    activity: {category.activity}
                    balance: {category.balance}
                    budgeted: {category.budgeted}
                ''')
                category_count += 1

        # Set the max goal to be 100. Need to flip the spent value as it is a negative number.
        total_goal = min((-total_spent / total_budgeted) * 100, 100)

        return {
            'balance': await cls.convert_to_float(total_balance),
            'budget': await cls.convert_to_float(total_budgeted),
            'spent': await cls.convert_to_float(-total_spent),
            'progress': total_goal
        }
