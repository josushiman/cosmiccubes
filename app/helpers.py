from tortoise.models import Model
from tortoise.exceptions import IntegrityError, OperationalError, FieldError
from fastapi import HTTPException
from uuid import UUID
from .models import Accounts, AccountTypes, BalanceTransfers, Budgets, Companies, CompanyCategories, DirectDebits, Mortgages, \
    Projects, ProjectItems, ProjectItemCategories
from .schemas import Accounts_Pydantic, AccountTypes_Pydantic, BalanceTransfers_Pydantic, Budgets_Pydantic, Companies_Pydantic, \
    CompanyCategories_Pydantic, DirectDebits_Pydantic, Mortgages_Pydantic, Projects_Pydantic, ProjectItems_Pydantic, \
    ProjectItemCategories_Pydantic

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
            "mortgages": Mortgages,
            "projects": Projects,
            "project-item-categories": ProjectItemCategories,
            "project-items": ProjectItems
        }

        try:
            return model_list[resource]
        except KeyError:
            raise HTTPException(status_code=404)
    
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
            "mortgages": Mortgages_Pydantic,
            "projects": Projects_Pydantic,
            "project-item-categories": ProjectItems_Pydantic,
            "project-items": ProjectItemCategories_Pydantic
        }

        try:
            return schema_list[resource]
        except KeyError:
            raise HTTPException(status_code=404)
    
    @classmethod
    async def get_one(cls, resource: str, _id: UUID) -> Model:
        # Get the pydantic schema, then the model.
        entity_schema = await cls.get_entity_schema(resource)
        entity_model = await cls.get_entity_model(resource)

        # Get the entity, then return it.
        return await entity_schema.from_queryset_single(entity_model.get(id=_id))

    @classmethod
    async def get_list(cls, resource: str, commons: dict, kwargs_raw: dict) -> tuple:
        # When an list of id's are provided, go straight to the get_many function.
        if 'id' in kwargs_raw and type(kwargs_raw['id']) is list: return await cls.get_many(resource, kwargs_raw['id'])

        # Otherwise process the kwargs, limit, and order values
        kwargs = await cls.process_raw_kwargs(kwargs_raw)
        order_by, limit = await cls.get_order_limit_value(commons)

        # TEMP - Get the model. But figure out how to swap this out so the bottom two things use Schema & Models
        model = await cls.get_entity_model(resource)

        # Make the DB requests to get the entities and count
        entities = await cls.get_entity_list_data(model, limit, commons["_start"], order_by, kwargs if kwargs != {} else None)
        row_count = await cls.get_entity_list_count(model, kwargs if kwargs != {} else None)

        # Load any reference data if needed.
        # entities = await cls.load_entities(model, entities)

        # Return it as a tuple.
        return entities, str(row_count)
    
    @classmethod
    async def get_many(cls, resource: str, ids: list[UUID]) -> tuple:
        results = []
        # Get each entity from the id's provided in the list.
        for entity_id in ids:
            db_entity = await cls.get_one(resource, entity_id)
            results.append(db_entity)

        return results, str(len(results))

    @classmethod
    async def create(cls, resource: str, resp_body: dict):
        # From the resource, get the Model and attempt to create it with kwargs.
        entity_model = await cls.get_entity_model(resource)

        # Create the entity
        try:
            return await entity_model.create(**resp_body)
        except AttributeError as e_attr:
            return # May have missed adding '_id' at the end of any FK relations in the json. e.g. type = type_id
        except IntegrityError as e_dupe:
            return

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
            # Get the sort value
            order_by = await cls.get_sort_value(commons["_order"], commons["_sort"])

        # Get the limit value
        limit = commons["_end"] - commons["_start"]

        if limit < 0:
            raise HTTPException(status_code=400, detail={
                "message": "End query parameter cannot be less than start query parameter."
            })

        return order_by, limit

    @classmethod
    async def get_sort_value(cls, order: str, sort: str) -> str:
        if order == "ASC":
            return sort
        return "-"+sort

    @classmethod
    async def get_entity_list_data(cls, model: Model, limit: int, offset: int, order_by: str = None, filter: dict = None) -> list[Model]:
        try:
            if order_by is None:
                if filter:
                    return await model.filter(**filter).limit(limit).offset(offset).all()
                return await model.all().limit(limit).offset(offset)
            elif filter is not None:
                return await model.filter(**filter).limit(limit).offset(offset).order_by(order_by).all()
            return await model.all().limit(limit).offset(offset).order_by(order_by)
        except OperationalError as e_opp:
            raise HTTPException(status_code=422, detail={
                "message": "Incorrect sort field provided."
            }) from e_opp
    
    @classmethod
    async def get_entity_list_count(cls, model: Model, filter: dict = None) -> int:
        if filter is not None:
            return await model.filter(**filter).count()
        return await model.all().count()

    @classmethod
    async def update(cls, resource: str, resp_body: dict, _id: UUID):
        # From the resource, get the Model and attempt to create it with kwargs.
        entity_model = await cls.get_entity_model(resource)

        try:
            return await entity_model.filter(id=_id).update(**resp_body)
        except FieldError as e_field:
            print("wrong field entered")
            return
        except IntegrityError as e_dupe:
            print("tried creating a dupe")
            return

    @classmethod
    async def delete(cls, resource: str, id: str):
        entity_model = await cls.get_entity_model(resource)

        deleted_count = await entity_model.filter(id=id).delete()
        if not deleted_count:
            print("didnt find entity")
        return
