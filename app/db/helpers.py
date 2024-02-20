import logging
from tortoise.models import Model
from tortoise.exceptions import IntegrityError, OperationalError, FieldError, ValidationError, DoesNotExist
from fastapi import HTTPException
from uuid import UUID
from .models import Accounts, AccountTypes, BalanceTransfers, Budgets, Companies, CompanyCategories, DirectDebits, Incomes, \
    Mortgages, Projects, ProjectItems, ProjectItemCategories, YnabAccounts, YnabCategories, YnabMonthSummaries, YnabPayees, \
    YnabServerKnowledge, YnabTransactions
from .schemas import Accounts_Pydantic, AccountTypes_Pydantic, BalanceTransfers_Pydantic, Budgets_Pydantic, Companies_Pydantic, \
    CompanyCategories_Pydantic, DirectDebits_Pydantic, Incomes_Pydantic, Mortgages_Pydantic, Projects_Pydantic, ProjectItems_Pydantic, \
    ProjectItemCategories_Pydantic, YnabAccounts_Pydantic, YnabCategories_Pydantic, YnabMonthSummaries_Pydantic, YnabPayees_Pydantic, \
    YnabServerKnowledge_Pydantic, YnabTransactions_Pydantic

# TODO make changes here to make sure can return Ynab stuff
class ReactAdmin():
    @classmethod
    async def get_entity_model(cls, resource: str) -> Model:
        model_list ={
            "accounts": Accounts,
            "account-types": AccountTypes,
            "balance-transfers": BalanceTransfers,
            "budgets": Budgets,
            "companies": Companies,
            "company-categories": CompanyCategories,
            "direct-debits": DirectDebits,
            "incomes": Incomes,
            "mortgages": Mortgages,
            "projects": Projects,
            "project-item-categories": ProjectItemCategories,
            "project-items": ProjectItems,
            "ynab-accounts": YnabAccounts,
            "ynab-categories": YnabCategories,
            "ynab-month-summaries": YnabMonthSummaries,
            "ynab-payees": YnabPayees,
            "ynab-server-knowledge": YnabServerKnowledge,
            "ynab-transaction": YnabTransactions
        }

        try:
            return model_list[resource]
        except KeyError:
            logging.warning(f"Model for {resource} doesn't exist.")
            raise HTTPException(status_code=400)
    
    @classmethod
    async def get_entity_schema(cls, resource: str):
        schema_list ={
            "accounts": Accounts_Pydantic,
            "account-types": AccountTypes_Pydantic,
            "balance-transfers": BalanceTransfers_Pydantic,
            "budgets": Budgets_Pydantic,
            "companies": Companies_Pydantic,
            "company-categories": CompanyCategories_Pydantic,
            "direct-debits": DirectDebits_Pydantic,
            "incomes": Incomes_Pydantic,
            "mortgages": Mortgages_Pydantic,
            "projects": Projects_Pydantic,
            "project-item-categories": ProjectItemCategories_Pydantic,
            "project-items": ProjectItems_Pydantic,
            "ynab-accounts": YnabAccounts_Pydantic,
            "ynab-categories": YnabCategories_Pydantic,
            "ynab-month-summaries": YnabMonthSummaries_Pydantic,
            "ynab-payees": YnabPayees_Pydantic,
            "ynab-server-knowledge": YnabServerKnowledge_Pydantic,
            "ynab-transaction": YnabTransactions_Pydantic
        }

        try:
            return schema_list[resource]
        except KeyError:
            logging.warning(f"Schema for {resource} doesn't exist.")
            raise HTTPException(status_code=400)
    
    @classmethod
    async def get_one(cls, resource: str, _id: UUID) -> Model:
        entity_model = await cls.get_entity_model(resource)
        entity_schema = await cls.get_entity_schema(resource)

        return await entity_schema.from_queryset_single(entity_model.get(id=_id))

    @classmethod
    async def get_list(cls, resource: str, commons: dict, kwargs_raw: dict) -> tuple:
        # When an list of id's are provided, go straight to the get_many function.
        if 'id' in kwargs_raw and type(kwargs_raw['id']) is list: 
            return await cls.get_many(resource, kwargs_raw['id'])

        kwargs = await cls.process_raw_kwargs(kwargs_raw)
        order_by, limit = await cls.get_order_limit_value(commons)

        entity_model = await cls.get_entity_model(resource)

        entities = await cls.get_entity_list_data(entity_model, resource, limit, commons["_start"], order_by, kwargs if kwargs != {} else None)
        row_count = await cls.get_entity_list_count(entity_model, kwargs if kwargs != {} else None)

        return entities, str(row_count)
    
    @classmethod
    async def get_many(cls, resource: str, ids: list[UUID]) -> tuple:
        results = []
        for entity_id in ids:
            db_entity = await cls.get_one(resource, entity_id)
            results.append(db_entity)

        return results, str(len(results))

    @classmethod
    async def create(cls, resource: str, resp_body: dict):
        entity_model = await cls.get_entity_model(resource)
        try:
            return await entity_model.create(**resp_body)
        except ValidationError as e_val:
            logging.info("Entity body failed validation.", exc_info=e_val)
            raise HTTPException(status_code=422) from e_val
        except AttributeError as e_attr:
            logging.info("Body is missing key attributes.")
            raise HTTPException(status_code=400) from e_attr # May have missed adding '_id' at the end of any FK relations in the json. e.g. type = type_id
        except IntegrityError as e_dupe:
            logging.info("Potentially trying to create a duplicate.", exc_info=e_dupe)
            raise HTTPException(status_code=409) from e_dupe

    @classmethod
    async def create_or_update(cls, resource: str, resp_body: dict, _id: UUID = None):
        logging.info(resp_body)
        try:
            resp_body.pop("id")
            entity = await cls.update(resource, resp_body, _id)
            logging.debug(f'Entity updated: {_id}')
        except DoesNotExist:
            # This error gets raised when trying to get an object which doesn't exist.
            logging.debug(f"This entity doesn't exist, creating a new one: {resp_body}")
            entity = await cls.create(resource, resp_body)
            logging.debug(f'Entity created: {entity.id}')
        except KeyError:
            logging.debug(f"This entity doesn't have an ID: {resp_body}")
            entity = await cls.create(resource, resp_body)
            logging.debug(f'Entity created: {entity.id}')

        return entity

    @classmethod
    async def process_raw_kwargs(cls, kwargs_raw: dict):
        # Only add values which exist from the request
        kwargs = {}
        for key, value in kwargs_raw.items():
            # Only store values which exist
            if value is not None:
                # Allow us to search the DB with like values
                if key == 'name': 
                    kwargs['name__icontains'] = value
                # Otherwise just store the value in the new dict
                else:
                    kwargs[key] = value
        return kwargs
    
    @classmethod
    async def get_order_limit_value(cls, commons: dict):
        order_by = None
        if commons["_order"] or commons["_sort"]:
            order_by = await cls.get_sort_value(commons["_order"], commons["_sort"])

        limit = commons["_end"] - commons["_start"]

        if limit < 0:
            logging.info("Limit value cannot be less than 0.")
            raise HTTPException(status_code=400)

        return order_by, limit

    @classmethod
    async def get_sort_value(cls, order: str, sort: str) -> str:
        if order == "ASC":
            return sort
        return "-"+sort

    @classmethod
    async def get_entity_list_data(cls, entity_model: Model, resource: str, limit: int, offset: int, order_by: str = None, filter: dict = None) -> list[Model]:
        entity_schema = await cls.get_entity_schema(resource)

        try:
            if order_by is None:
                if filter:
                    return await entity_schema.from_queryset(entity_model.filter(**filter).limit(limit).offset(offset))
                return await entity_schema.from_queryset(entity_model.all().limit(limit).offset(offset))
            elif filter is not None:
                return await entity_schema.from_queryset(entity_model.filter(**filter).limit(limit).offset(offset).order_by(order_by))
            return await entity_schema.from_queryset(entity_model.all().limit(limit).offset(offset).order_by(order_by))
        except OperationalError as e_opp:
            logging.info("Incorrect sort field provided.")
            raise HTTPException(status_code=422) from e_opp
    
    @classmethod
    async def get_entity_list_count(cls, entity_model: Model, filter: dict = None) -> int:
        if filter is not None:
            return await entity_model.filter(**filter).count()
        return await entity_model.all().count()

    @classmethod
    async def update(cls, resource: str, resp_body: dict, _id: UUID):
        entity_model = await cls.get_entity_model(resource)

        try:
            await entity_model.filter(id=_id).update(**resp_body)
            return await cls.get_one(resource, _id)
        except FieldError as e_field:
            logging.info("Incorrect fields being passed to the model.")
            raise HTTPException(status_code=422) from e_field
        except IntegrityError as e_dupe:
            logging.info("Potentially trying to create a duplicate.")
            raise HTTPException(status_code=409) from e_dupe

    @classmethod
    async def delete(cls, resource: str, id: str):
        entity_model = await cls.get_entity_model(resource)

        deleted_count = await entity_model.filter(id=id).delete()
        if not deleted_count:
            logging.info("Couldn't find entity to delete.")
        return deleted_count
