import logging
from datetime import datetime
from fastapi import HTTPException
from tortoise.models import Model
from tortoise.exceptions import FieldError, IntegrityError
from app.db.models import YnabServerKnowledge, YnabAccounts, YnabCategories, YnabMonthSummaries, YnabMonthDetailCategories, YnabPayees, \
    YnabTransactions
from app.config import settings

class YnabServerKnowledgeHelper():
    @classmethod
    async def add_server_knowledge_to_url(cls, ynab_url: str, server_knowledge: int) -> bool:
        # If a ? exists in the URL then append the additional param.
        if '?' in ynab_url:
            return f"{ynab_url}&server_knowledge={server_knowledge}"
            
        # Otherwise add a ? and include the sk param.
        return f"{ynab_url}?server_knowledge={server_knowledge}"

    @classmethod
    async def check_if_exists(cls, route_url: str) -> YnabServerKnowledge | None:
        return await YnabServerKnowledge.get_or_none(route=route_url)

    @classmethod
    async def check_route_eligibility(cls, action: str) -> bool:
        capable_routes = ['accounts-list','categories-list','months-list','payees-list','transactions-list']
        return action in capable_routes

    @classmethod
    async def create_update_route_entities(cls, resp_body: dict, model: Model) -> int:
        try:
            obj = await model.create(**resp_body)
            logging.debug(f"New entity created {obj.id}")
            return 1
        except IntegrityError:
            try:
                entity_id = resp_body["id"]
                resp_body.pop("id")
            except KeyError: # Happens on 'months-list' as no ID is returned.
                resp_month_dt = datetime.strptime(resp_body['month'], '%Y-%m-%d')
                db_entity = await model.filter(month=resp_month_dt).get()
                entity_id = db_entity.id
                resp_body.pop("month") # Need to pop the month as it doesnt need to be updated.
            obj = await model.filter(id=entity_id).update(**resp_body)
            logging.debug(f"Entity updated")
            return 0
        except FieldError as e_field:
            logging.exception("Issue with a field value", exc_info=e_field)
            return 0
        except Exception as exc:
            logging.exception("Issue create/update entity.", exc_info=exc)
            return 0

    @classmethod
    async def create_update_server_knowledge(cls, route: str, server_knowledge: int,
        db_entity: YnabServerKnowledge = None) -> YnabServerKnowledge:
        try:
            if db_entity:
                logging.debug(f"Updating server knowledge for {route} to {server_knowledge}")
                db_entity.last_updated = datetime.today()
                db_entity.server_knowledge = server_knowledge
                await db_entity.save()
                return db_entity
            logging.debug(f"Creating server knowledge for {route} to {server_knowledge}")
            return await YnabServerKnowledge.create(
                budget_id=settings.ynab_budget_id,
                route=route,
                last_updated=datetime.today(),
                server_knowledge=server_knowledge
            )
        except Exception as exc:
            logging.exception("Issue create/update server knowledge.", exc_info=exc)
            raise HTTPException(status_code=500)
    
    @classmethod
    async def current_date_check(cls, date_to_check: datetime) -> bool:
        current_date = datetime.today().strftime('%Y-%m-%d')
        date_to_check = date_to_check.strftime('%Y-%m-%d')
        logging.debug(f"Checking if {current_date} is the same as {date_to_check}")
        return current_date == date_to_check
    
    @classmethod
    async def get_route_data_name(cls, action: str) -> str | HTTPException:
        data_name_list = {
            "accounts-list": "accounts",
            "categories-list": "category_groups",
            "months-list": "months",
            "payees-list": "payees",
            "transactions-list": "transactions"
        }

        try:
            logging.debug(f"Attempting to get a data name for {action}")
            return data_name_list[action]
        except KeyError:
            logging.warning(f"Data name for {action} doesn't exist.")
            raise HTTPException(status_code=400)

    @classmethod
    async def get_sk_model(cls, action: str) -> Model | HTTPException:
        model_list = {
            "accounts-list": YnabAccounts,
            "categories-list": YnabCategories,
            "months-single": YnabMonthDetailCategories,
            "months-list": YnabMonthSummaries,
            "payees-list": YnabPayees,
            "transactions-list": YnabTransactions
        }

        try:
            logging.debug(f"Attempting to get a model for {action}")
            return model_list[action]
        except KeyError:
            logging.warning(f"Model for {action} doesn't exist.")
            raise HTTPException(status_code=400)
    
    @classmethod
    async def process_entities(cls, action: str, entities: dict) -> dict:
        model = await cls.get_sk_model(action)

        if action == 'categories-list':
            # Need to loop on each of the category groups as they are not presented as one full list.
            entity_list = []
            for group in entities:
                for category in group["categories"]:
                    entity_list.append(category)
            logging.debug(f"List of categories {entity_list}.")
        else:
            entity_list = entities

        created = 0
        for entity in entity_list:
            logging.debug(entity)
            if action == 'transactions-list':
                entity.pop('flag_name') # new field introduced. TODO figure out how to do DB migrations
                entity.pop('subtransactions')
            obj = await cls.create_update_route_entities(resp_body=entity, model=model)
            created += obj
        
        logging.debug(f"Created {created} entities. Updated {len(entities) - created} entities")
        return { "message": "Complete" }
