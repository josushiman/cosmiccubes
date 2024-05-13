import logging
import re
from datetime import datetime, UTC
from fastapi import HTTPException
from tortoise.models import Model
from tortoise.exceptions import (
    IncompleteInstanceError,
    IntegrityError,
    FieldError,
)
from deepdiff import DeepDiff
from app.db.models import (
    YnabServerKnowledge,
    YnabAccounts,
    YnabCategories,
    YnabMonthSummaries,
    YnabMonthDetailCategories,
    YnabPayees,
    YnabTransactions,
)
from app.config import settings


class YnabServerKnowledgeHelper:
    negative_amounts = [
        YnabTransactions,
        YnabMonthSummaries,
        YnabMonthDetailCategories,
        YnabCategories,
        YnabAccounts,
    ]

    @classmethod
    async def create_switch_negative_values(cls, model: Model) -> Model:
        if type(model) == YnabAccounts:
            if model.balance < 0:
                model.balance = -model.balance
            if model.cleared_balance < 0:
                model.cleared_balance = -model.cleared_balance
            if model.uncleared_balance < 0:
                model.uncleared_balance = -model.uncleared_balance
        elif type(model) == YnabCategories or type(model) == YnabMonthDetailCategories:
            if model.activity < 0:
                model.activity = -model.activity
            if model.balance < 0:
                model.balance = -model.balance
        elif type(model) == YnabMonthSummaries:
            if model.activity < 0:
                model.activity = -model.activity
        elif type(model) == YnabTransactions:
            if model.amount < 0:
                model.amount = -model.amount

        return model

    @classmethod
    async def update_switch_negative_values(
        cls, model: Model, resp_body: dict
    ) -> Model:
        if type(model) == YnabAccounts:
            if resp_body["balance"] < 0:
                resp_body["balance"] = -resp_body["balance"]
            if resp_body["cleared_balance"] < 0:
                resp_body["cleared_balance"] = -resp_body["cleared_balance"]
            if resp_body["uncleared_balance"] < 0:
                resp_body["uncleared_balance"] = -resp_body["uncleared_balance"]
        elif type(model) == YnabCategories or type(model) == YnabMonthDetailCategories:
            if resp_body["activity"] < 0:
                resp_body["activity"] = -resp_body["activity"]
            if resp_body["balance"] < 0:
                resp_body["balance"] = -resp_body["balance"]
        elif type(model) == YnabMonthSummaries:
            if resp_body["activity"] < 0:
                resp_body["activity"] = -resp_body["activity"]
        elif type(model) == YnabTransactions:
            if resp_body["amount"] < 0:
                resp_body["amount"] = -resp_body["amount"]

        return resp_body

    @classmethod
    async def add_server_knowledge_to_url(
        cls, ynab_url: str, server_knowledge: int
    ) -> bool:
        # If a ? exists in the URL then append the additional param.
        if "?" in ynab_url:
            return f"{ynab_url}&last_knowledge_of_server={server_knowledge}"

        # Otherwise add a ? and include the sk param.
        return f"{ynab_url}?last_knowledge_of_server={server_knowledge}"

    @classmethod
    async def check_if_exists(cls, route_url: str) -> YnabServerKnowledge | None:
        return await YnabServerKnowledge.get_or_none(route=route_url)

    @classmethod
    async def check_route_eligibility(cls, action: str) -> bool:
        capable_routes = [
            "accounts-list",
            "categories-list",
            "months-list",
            "payees-list",
            "transactions-list",
        ]
        return action in capable_routes

    @classmethod
    async def create_route_entities(cls, model: Model) -> int | IntegrityError:
        if type(model) == YnabTransactions:
            model.debit = False if model.amount > 0 else True

        if type(model) in cls.negative_amounts:
            model = await cls.create_switch_negative_values(model)

        try:
            await model.save()
            return 1
        except IncompleteInstanceError as e_incomplete:
            logging.exception(
                "Model is partial and the fields are not available for persistence",
                exc_info=e_incomplete,
            )
            return 0
        except IntegrityError:
            raise IntegrityError

    @classmethod
    async def create_update_server_knowledge(
        cls, route: str, server_knowledge: int, db_entity: YnabServerKnowledge = None
    ) -> YnabServerKnowledge:
        try:
            if db_entity:
                logging.debug(
                    f"Updating server knowledge for {route} to {server_knowledge}"
                )
                db_entity.last_updated = datetime.today()
                db_entity.server_knowledge = server_knowledge
                await db_entity.save()
                return db_entity
            logging.debug(
                f"Creating server knowledge for {route} to {server_knowledge}"
            )
            return await YnabServerKnowledge.create(
                budget_id=settings.ynab_budget_id,
                route=route,
                last_updated=datetime.today(),
                server_knowledge=server_knowledge,
            )
        except Exception as exc:
            logging.exception("Issue create/update server knowledge.", exc_info=exc)
            raise HTTPException(status_code=500)

    @classmethod
    async def get_route_data_name(cls, action: str) -> str | HTTPException:
        data_name_list = {
            "accounts-list": "accounts",
            "categories-list": "category_groups",
            "months-list": "months",
            "payees-list": "payees",
            "transactions-list": "transactions",
        }

        try:
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
            "transactions-list": YnabTransactions,
        }

        try:
            return model_list[action]
        except KeyError:
            logging.warning(f"Model for {action} doesn't exist.")
            raise HTTPException(status_code=400)

    @classmethod
    async def pop_new_field_from_response(
        cls, resp_body: dict, new_items_added: list[str]
    ) -> dict:
        logging.debug(
            f"{len(new_items_added)} new field(s) from YNAB attempting to remove them."
        )

        pattern = r"root\['([^']+)'\]"

        for new_field in new_items_added:
            match = re.search(pattern, new_field)
            try:
                key_to_pop = match.group(1)
            except IndexError:
                logging.error("Issue with regex trying to extract key to pop.")
                raise IndexError
            resp_body.pop(key_to_pop)
            logging.debug(f"Removed {new_field} from the response body.")

        return resp_body

    @classmethod
    async def remove_unused_fields(cls, model: Model, resp_body: dict) -> dict:
        # Get the DB fields (returns a set)
        db_fields = model._meta.db_fields
        resp_fields = set(resp_body.keys())

        diff = DeepDiff(t1=db_fields, t2=resp_fields)

        try:
            new_items_added = diff["set_item_added"]
        except KeyError:
            return resp_body

        if new_items_added:
            resp_body = await cls.pop_new_field_from_response(
                resp_body=resp_body, new_items_added=new_items_added
            )

        return resp_body

    @classmethod
    async def update_route_entities(cls, model: Model, resp_body: dict) -> int:
        try:
            entity_id = resp_body["id"]
            resp_body.pop("id")
        except KeyError:  # Happens on 'months-list' as no ID is returned.
            resp_month_dt = datetime.strptime(resp_body["month"], "%Y-%m-%d")
            resp_month_dt = resp_month_dt.replace(
                tzinfo=UTC
            )  # This can fail if there are timezone issues. So ensure the TZ is set.
            # logging.debug(f"datetime has been set to: {resp_month_dt}")
            db_entity = await model.filter(month=resp_month_dt).get()
            entity_id = db_entity.id
            resp_body.pop(
                "month"
            )  # Need to pop the month as it doesnt need to be updated.

        # Make sure all the fields which aren't supported on the DB are removed.
        resp_body = await cls.remove_unused_fields(model=model, resp_body=resp_body)

        # Make sure any dates passed into the update is a datetime value, not a string if its a transaction.
        if type(model) == YnabTransactions:
            resp_body["debit"] = False if resp_body["amount"] > 0 else True

            # Set the category ID for those that may have changed.
            resp_body["category_fk_id"] = resp_body["category_id"]
            logging.debug(
                f"Attempting to set Category to transaction: {resp_body['category_id']}"
            )

            try:
                raw_date = resp_body.get("date")
                resp_date_dt = datetime.strptime(raw_date, "%Y-%m-%d")
                resp_date_dt = resp_date_dt.replace(tzinfo=UTC)
                resp_body["date"] = resp_date_dt
                # logging.debug(f"Converted datetime: {resp_date_dt}")
            except KeyError:
                logging.warning("No date in response body.")

        if type(model) in cls.negative_amounts:
            resp_body = await cls.update_switch_negative_values(model, resp_body)

        try:
            await model.filter(id=entity_id).update(**resp_body)
            logging.debug("Entity updated.")
            return 1
        except FieldError as e_field:
            logging.warning("Additional field identified in model", exc_info=e_field)
            return 0

    @classmethod
    async def process_entities(cls, action: str, entities: dict) -> dict:
        if action == "categories-list":
            # Need to loop on each of the category groups as they are not presented as one full list.
            entity_list = []
            for group in entities:
                for category in group["categories"]:
                    entity_list.append(category)
        else:
            entity_list = entities

        created = 0
        skipped = 0
        updated = 0
        logging.info(f"Processing {len(entity_list)} entities.")
        for entity in entity_list:
            if entity["deleted"] == True:
                skipped += 1
                continue

            model = await YnabModelResponses.return_sk_model(
                action=action, kwargs=entity
            )
            # logging.debug(f"Model body: {entity}")
            try:
                created += await cls.create_route_entities(model=model)
            except IntegrityError:
                if type(model) == YnabPayees:
                    # Payees do not change once entered. No need to update them.
                    skipped += 1
                    continue
                updated += await cls.update_route_entities(
                    model=model, resp_body=entity
                )

        logging.debug(
            f"""
            Created: {created}
            Updated: {updated}
            Skipped: {skipped}
            Issues: {len(entities) - (created + updated + skipped)}
            """
        )
        return {"message": "Complete"}


class YnabModelResponses:
    @classmethod
    async def return_sk_model(cls, action: str, kwargs: dict) -> Model | HTTPException:
        match action:
            case "accounts-list":
                return await cls.create_account(kwargs=kwargs)
            case "categories-list":
                return await cls.create_category(kwargs=kwargs)
            case "months-single":
                return await cls.create_month_detail(kwargs=kwargs)
            case "months-list":
                return await cls.create_month_summary(kwargs=kwargs)
            case "payees-list":
                return await cls.create_payee(kwargs=kwargs)
            case "transactions-list":
                # Two fields which should be ignored
                # flag_name, subtransactions
                return await cls.create_transactions(kwargs=kwargs)
            case _:
                logging.warning(f"Model for {action} doesn't exist.")
                raise HTTPException(status_code=400)

    @classmethod
    async def create_account(cls, kwargs: dict) -> YnabAccounts:
        return YnabAccounts(**kwargs)

    @classmethod
    async def create_category(cls, kwargs: dict) -> YnabCategories:
        return YnabCategories(**kwargs)

    @classmethod
    async def create_month_detail(cls, kwargs: dict) -> YnabMonthDetailCategories:
        return YnabMonthDetailCategories(**kwargs)

    @classmethod
    async def create_month_summary(cls, kwargs: dict) -> YnabMonthSummaries:
        return YnabMonthSummaries(**kwargs)

    @classmethod
    async def create_payee(cls, kwargs: dict) -> YnabPayees:
        return YnabPayees(**kwargs)

    @classmethod
    async def create_transactions(cls, kwargs: dict) -> YnabTransactions:
        return YnabTransactions(**kwargs)
