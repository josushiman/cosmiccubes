import logging
import httpx
import json
import calendar
from async_lru import alru_cache
from enum import Enum, IntEnum
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pydantic import TypeAdapter
from fastapi import HTTPException
from tortoise.models import Model
from app.ynab.serverknowledge import YnabServerKnowledgeHelper
from app.db.models import YnabServerKnowledge, YnabAccounts, YnabCategories, YnabMonthSummaries, YnabMonthDetailCategories, YnabPayees, \
    YnabTransactions
from app.ynab.models import AccountsResponse, CategoriesResponse, MonthSummariesResponse, PayeesResponse, \
    TransactionsResponse, Account, Category, MonthSummary, MonthDetail, Payee, TransactionDetail
from app.config import settings

class YnabHelpers():
    @classmethod
    async def get_date_for_transactions(cls, year: Enum = None, months: IntEnum = None, specific_month: Enum = None) -> str:
        logging.debug(f'''
        Year: {year}
        Months: {months}
        Specific Month: {specific_month}
        ''')
        if year and not specific_month:
            date_value = datetime.today().replace(year=int(year.value), month=1, day=1).strftime('%Y-%m-%d')
            return date_value
        
        if specific_month and year:
            date_value = datetime.today().replace(year=int(year.value), month=int(specific_month.value), day=1).strftime('%Y-%m-%d')
            return date_value
        
        if specific_month:
            date_value = datetime.today().replace(month=int(specific_month.value), day=1).strftime('%Y-%m-%d')
            return date_value
        
        # If this condition is not set, it'll always return the current month, which would also meet the need for months=1
        if months:
            current_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # When returning months, you need to include the current month. So you therefore need to subtract 1 from the months value.
            month_delta = current_date - relativedelta(months=months - 1)
            return month_delta.strftime('%Y-%m-%d')
    
        return datetime.today().replace(day=1).strftime('%Y-%m-%d')

    @classmethod
    async def get_last_date_from_since_date(cls, since_date: str, year: bool = False) -> datetime:
        since_date_dt = datetime.strptime(since_date, '%Y-%m-%d')
        _, last_day = calendar.monthrange(since_date_dt.year, since_date_dt.month)
        if year:
            return datetime(year=since_date_dt.year, month=12, day=last_day, hour=23, minute=59, second=59)
        return datetime(year=since_date_dt.year, month=since_date_dt.month, day=last_day, hour=23, minute=59, second=59)

    @classmethod
    async def get_days_left_from_current_month(cls) -> datetime:
        today = datetime.today().replace(hour=0, minute=0, second=0)
        last_day_of_month = await cls.get_last_date_from_since_date(today.strftime('%Y-%m-%d'))

        days_left = (last_day_of_month - today).days
        
        return days_left

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
                # month -> The budget month in ISO format (e.g. 2016-12-01)
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

    @classmethod
    async def get_pydantic_model(cls, action: str) -> Model | HTTPException:
        model_list = {
            "accounts-list": Account,
            "categories-list": Category,
            "months-list": MonthSummary,
            "months-single": MonthDetail,
            "payees-list": Payee,
            "transactions-list": TransactionDetail
        }

        try:
            logging.debug(f"Attempting to get pydantic model for {action}")
            return model_list[action]
        except KeyError:
            logging.warning(f"Pydantic model for {action} doesn't exist.")
            raise HTTPException(status_code=400)

    @classmethod
    async def check_server_knowledge_status(cls, action: str, param_1: str = None) -> tuple[bool, YnabServerKnowledge | None]:
        sk_route = await cls.get_route(action, param_1)
        server_knowledge = await YnabServerKnowledgeHelper.check_if_exists(route_url=sk_route)

        # Return False if no entry of SK exists.
        if not server_knowledge: 
            logging.warning(f"No server knowledge found for {sk_route}")
            return False, None

        is_up_to_date = await YnabServerKnowledgeHelper.current_date_check(server_knowledge.last_updated)
        if is_up_to_date:
            logging.debug("Route is up to date.")
            return True, server_knowledge
        logging.info("Route is out of date, attempting to run a HTTP request to YNAB.")
        return False, server_knowledge

    @classmethod
    @alru_cache(maxsize=32) # Caches requests so we don't overuse them.
    async def make_request(cls,
            action: str,
            param_1: str = settings.ynab_budget_id,
            param_2: str = None,
            since_date: str = None,
            month: str = None,
            year: Enum = None
        ) -> dict | HTTPException:
        '''
        Check if the route exists in server knowledge
            If it does, check the entities are up to date
                If they are return the DB entities
            If they're not, make the api call
        Once the API call is made, save them to the DB
            Then return the DB entities
        '''
        ynab_route = await cls.get_route(action, param_1, param_2, since_date, month)
        ynab_url = settings.ext_ynab_url + ynab_route

        sk_eligible = await YnabServerKnowledgeHelper.check_route_eligibility(action=action)
        sk_up_to_date, server_knowledge = await cls.check_server_knowledge_status(action=action, param_1=param_1)

        if sk_up_to_date:
            logging.info("Date is the same as today, returning the DB entities.")
            return await cls.return_db_model_entities(action=action, since_date=since_date, month=month, year=year)
        elif not sk_up_to_date and server_knowledge:
            logging.debug(f"Updating ynab url to include server_knowledge value: {ynab_url}")
            ynab_url = await YnabServerKnowledgeHelper.add_server_knowledge_to_url(
                ynab_url=ynab_url,
                server_knowledge=server_knowledge.server_knowledge
            )

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(ynab_url, headers={'Authorization': f"Bearer {settings.ext_ynab_token}"})
            except httpx.HTTPError as exc:
                logging.exception(exc)
                raise HTTPException(status_code=500)
            finally:
                if sk_eligible:
                    return await cls.process_sk_route_request(
                        response=response,
                        action=action,
                        param_1=param_1,
                        server_knowledge=server_knowledge,
                        since_date=since_date,
                        month=month,
                        year=year
                    )
                logging.info("Route is not sk eligible, returning the JSON response w/ pydantic models.")
                return await cls.return_pydantic_model_entities(json_response=response.json(), action=action)

    @classmethod
    async def process_sk_route_request(cls,
            response: json,
            action: str,
            param_1: str,
            server_knowledge: YnabServerKnowledge,
            since_date: str = None,
            month: str = None,
            year: Enum = None
        ) -> list[Model]:
        logging.debug("Updating/creating new entities")
        action_data_name = await YnabServerKnowledgeHelper.get_route_data_name(action)
        resp_entity_list = response.json()["data"][action_data_name]
        await YnabServerKnowledgeHelper.process_entities(action=action, entities=resp_entity_list)
        resp_server_knowledge = response.json()["data"]["server_knowledge"]
        sk_route = await cls.get_route(action, param_1)
        await YnabServerKnowledgeHelper.create_update_server_knowledge(
            route=sk_route,
            server_knowledge=resp_server_knowledge,
            db_entity=server_knowledge
        )
        logging.debug("Server knowledge created/updated.")
        return await cls.return_db_model_entities(action=action, since_date=since_date, month=month, year=year)

    @classmethod
    async def pydantic_accounts(cls) -> list[YnabAccounts]:
        return await cls.make_request('accounts-list')
    
    @classmethod
    async def pydantic_categories(cls) -> list[YnabCategories]:
        return await cls.make_request('categories-list')
    
    @classmethod
    async def pydantic_month_details(cls) -> list[YnabMonthSummaries]:
        current_month = datetime.today().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_month = current_month - relativedelta(months=1)
        prev_month_string = previous_month.strftime('%Y-%m-%d')
        # Check if the previous month categories exist in the DB
        logging.debug(f"Checking if any previous month categories exist for {prev_month_string}")
        prev_month_entities = await YnabMonthDetailCategories.filter(month_summary_fk__month=previous_month).all()
        # If its already been stored, skip it otherwise make the API call.
        if len(prev_month_entities) > 0: return { "message": "Already stored for the previous month" }
        # Get the month summary
        month_summary_entity = await YnabMonthSummaries.filter(month=previous_month).get_or_none()
        if month_summary_entity is None: return {"message": "no month summary available. run update_month_summaries."}
        # Get the entities to store
        json_month_list = await cls.make_request('months-single', month=prev_month_string)
        # Then store the entities in the DB.
        for category in json_month_list:
            category["month_summary_fk"] = month_summary_entity

        await YnabServerKnowledgeHelper.process_entities(action='months-single', entities=json_month_list)
        return { "message": "Complete" }

    @classmethod
    async def pydantic_month_summaries(cls) -> list[YnabMonthSummaries]:
        return await cls.make_request('months-list')

    @classmethod
    async def pydantic_payees(cls) -> list[YnabPayees]:
        return await cls.make_request('payees-list')
    
    @classmethod
    async def pydantic_transactions(cls, since_date: str = None, month: str = None, year: Enum = None) -> list[YnabTransactions]:
        return await cls.make_request('transactions-list', since_date=since_date, month=month, year=year)

    @classmethod
    async def return_db_model_entities(cls, action: str, since_date: str = None, month: Enum = None, year: Enum = None) -> list[Model]:
        logging.info("Returning DB entities.")
        db_model = await YnabServerKnowledgeHelper.get_sk_model(action=action)
        if since_date and not (year and month):
            todays_date = datetime.today().strftime('%Y-%m-%d')
            logging.debug(f"Returning DB entities from {since_date} to {todays_date}")
            queryset = db_model.filter(date__range=(since_date, todays_date)).order_by('-date') # DESC
        elif month and year:
            # Convert since_date to datetime
            since_date = datetime(int(year.value), int(month.value), 1)
            # Find the first day of the next month
            first_day_of_next_month = since_date + timedelta(days=32)
            # Calculate the last day of the current month
            last_day_of_month = first_day_of_next_month.replace(day=1) - timedelta(days=1)
            to_date = last_day_of_month.strftime('%Y-%m-%d')
            # Set the from date to the last day of that month.
            logging.debug(f"Returning transactions for the entire month of {since_date.strftime('%Y-%m-%d')} - {to_date}")
            queryset = db_model.filter(date__range=(since_date, to_date)).order_by('-date') # DESC
        else:
            logging.debug("Returning all entities.")
            if action == 'transactions-list':
                queryset = db_model.all().order_by('-date')
            else:
                queryset = db_model.all()

        # Make the DB call, and return them as dicts
        db_entities = await queryset.values()

        # Return the entities as if they were pydantic models from ynab.
        db_pydantic_model = await cls.get_pydantic_model(action=action)
        return TypeAdapter(list[db_pydantic_model]).validate_python(db_entities)

    @classmethod
    async def return_pydantic_model_entities(cls, json_response: json, action: str) -> list[Model]:
        match action:
            case 'accounts-list':
                pydantic_accounts_list = AccountsResponse.model_validate_json(json.dumps(json_response))
                return pydantic_accounts_list.data.accounts
            case 'categories-list':
                pydantic_categories_list = CategoriesResponse.model_validate_json(json.dumps(json_response))
                return pydantic_categories_list.data.category_groups
            case 'months-single':
                return json_response["data"]["month"]["categories"]
            case 'months-list':
                pydantic_months_list = MonthSummariesResponse.model_validate_json(json.dumps(json_response))
                return pydantic_months_list.data.months
            case 'payees-list':
                pydantic_payees_list = PayeesResponse.model_validate_json(json.dumps(json_response))
                return pydantic_payees_list.data.payees
            case 'transactions-list':
                pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(json_response))
                return pydantic_transactions_list.data.transactions
            case _:
                logging.exception(f"Tried to return an endpoint we don't support yet. {action}")
                raise HTTPException(status_code=500)

    @classmethod
    async def sync_transaction_rels(cls):
        # Get all the transactions that don't have a category_fk set
        transactions_no_cat_fk = await YnabTransactions.filter(category_fk=None)
        transactions_to_update = await YnabTransactions.filter(category_fk=None).count()

        if transactions_to_update < 1: return {"message": "All transactions have category fk's synced."}

        skipped_transactions = 0
        # Go through each transaction that doesn't have a category_fk set
        for transaction in transactions_no_cat_fk:
            # Search on the ynabcategories table for the ID
            category_entity = await YnabCategories.filter(id=transaction.category_id).get_or_none()

            if category_entity is None:
                if transaction.transfer_account_id is not None:
                    logging.debug(f"Transaction is a transfer, ignoring: {transaction.id}")    
                else:
                    logging.warn(f"Category may not be set for transaction: {transaction.id}")
                skipped_transactions += 1
                continue
            
            # Set the category_fk
            logging.debug(f"Assigning Category Group: {category_entity.category_group_name} to {transaction.id}")
            transaction.category_fk = category_entity
            await transaction.save()

        logging.info(f'''
        Total to sync: {transactions_to_update}
        Total skipped: {skipped_transactions}
        Total synced: {transactions_to_update-skipped_transactions}
        ''')
        return {"message": "Complete."}
