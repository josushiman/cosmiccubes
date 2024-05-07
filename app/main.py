import logging
import newrelic.agent
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tortoise import Tortoise
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Depends, Query, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
from app.config import settings
from app.reactadmin.helpers import ReactAdmin as ra
from app.enums import (
    PeriodMonthOptionsIntEnum,
    SpecificMonthOptionsEnum,
    SpecificYearOptionsEnum,
)
from app.ynab.main import YNAB as ynab
from app.ynab.helpers import YnabHelpers as ynab_help

dotenv_token = settings.env_token
dotenv_hosts = settings.env_hosts
dotenv_origins = settings.env_origins
dotenv_referer = settings.env_referer
dotenv_docs = settings.env_docs
dotenv_user_agent = settings.env_agent
dotenv_path_to_ini = settings.newrelic_ini_path

logging.info("Initialising NewRelic")
newrelic.agent.initialize(dotenv_path_to_ini, settings.newrelic_env)

scheduler = AsyncIOScheduler()


async def update_account_data():
    try:
        await update_accounts()
    except Exception as e_exc:
        logging.error(f"issue updating endpoint {update_accounts}", exc_info=e_exc)


async def update_category_data():
    try:
        await update_categories()
    except Exception as e_exc:
        logging.error(f"issue updating endpoint {update_accounts}", exc_info=e_exc)


async def update_payee_data():
    try:
        await update_payees()
    except Exception as e_exc:
        logging.error(f"issue updating endpoint {update_payees}", exc_info=e_exc)


async def update_month_detail_data():
    try:
        await update_month_details()
    except Exception as e_exc:
        logging.error(f"issue updating endpoint {update_month_details}", exc_info=e_exc)


async def update_month_summary_data():
    try:
        await update_month_summaries()
    except Exception as e_exc:
        logging.error(
            f"issue updating endpoint {update_month_summaries}", exc_info=e_exc
        )


async def update_transaction_data():
    try:
        await update_transactions()
    except Exception as e_exc:
        logging.error(f"issue updating endpoint {update_transactions}", exc_info=e_exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initialising DB")
    await Tortoise.init(
        db_url=settings.db_url,
        modules={"models": ["app.db.models"]},
    )
    # Generate the model schemas.
    logging.info("Generating schemas.")
    await Tortoise.generate_schemas()
    logging.info("Schemas generated.")
    logging.info("Starting scheduler.")
    if settings.newrelic_env != "development":
        scheduler.add_job(update_account_data, trigger="cron", hour="*", minute=4)
        scheduler.add_job(update_category_data, trigger="cron", hour="*", minute=5)
        scheduler.add_job(update_payee_data, trigger="cron", hour="*", minute=6)
        scheduler.add_job(update_month_detail_data, trigger="cron", hour="*", minute=8)
        scheduler.add_job(update_month_summary_data, trigger="cron", hour="*", minute=9)
        scheduler.add_job(update_transaction_data, trigger="cron", hour="*", minute=10)
        scheduler.add_job(update_savings, trigger="cron", day="*/2", hour=4, minute=30)
    scheduler.start()
    yield
    # Close all connections when shutting down.
    logging.info("Shutting down scheduler.")
    scheduler.shutdown()
    logging.info("Shutting down application.")
    await Tortoise.close_connections()


async def get_token_header(request: Request, x_token: UUID = Header(...)):
    if dotenv_origins != ["*"] or dotenv_hosts != ["*"]:
        logging.debug(request.headers.raw)
        try:
            referer = request.headers["referer"]
            host = request.headers["host"]
            if referer != dotenv_referer:
                logging.debug(f"Referer: {referer}")
                logging.warning(
                    f"Referer {referer} attempted access using a valid token"
                )
                raise HTTPException(status_code=403)
            if dotenv_hosts != host:
                logging.debug(f"Host: {host}")
                logging.warning(f"Host {host} attempted access using a valid token")
                raise HTTPException(status_code=403)
        except KeyError as e_key:
            logging.warning(f"Either Referer or Host was not set", exc_info=e_key)
            raise HTTPException(status_code=403)

        try:
            origin = request.headers["origin"]
            if origin != dotenv_origins:
                logging.debug(f"Origin: {origin}")
                logging.warning(f"Origin {origin} attempted access using a valid token")
                raise HTTPException(status_code=403)
        except KeyError as e_key:
            user_agent = request.headers["user-agent"]
            if user_agent != dotenv_user_agent:
                logging.warning(
                    f"Origin was not set for {request.headers['host']} on IP: {request.headers['true-client-ip']}. User Agent string: {user_agent}"
                )

    if x_token != dotenv_token:
        logging.warning(f"Invalid token provided from Origin and/or Host")
        raise HTTPException(status_code=403)


logging.debug(f"{dotenv_docs}")
logging.debug(f"{dotenv_hosts}, {dotenv_origins}, {dotenv_referer}")

app = FastAPI(
    lifespan=lifespan,
    dependencies=[Depends(get_token_header)],
    openapi_url=dotenv_docs,
)


async def token_override():
    # This override means it will accept any UUID thats used when making calls on the development environment only.
    return


if settings.newrelic_env == "development":
    app.dependency_overrides[get_token_header] = token_override

app.add_middleware(
    CORSMiddleware,
    allow_origins=[dotenv_origins],
    expose_headers=["x-total-count"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def common_ra_parameters(
    _end: int = 10,
    _start: int = 0,
    _order: str = Query(default="ASC", min_length=3, max_length=4, regex="ASC|DESC"),
    _sort: str = None,
):
    return {"_end": _end, "_start": _start, "_order": _order, "_sort": _sort}


async def common_cc_parameters(
    year: SpecificYearOptionsEnum = None,
    months: PeriodMonthOptionsIntEnum = None,
    month: SpecificMonthOptionsEnum = None,
):
    return {"year": year, "months": months, "month": month}


@app.get("/health", status_code=200)
async def get_health():
    return {"status": "OK"}


@app.post("/portal/admin/{resource}", status_code=201, include_in_schema=False)
async def create(resource: str, _body: dict):
    return await ra.create(resource, _body)


@app.get("/portal/admin/{resource}/{_id}")
async def get_one(resource: str, _id: UUID):
    return await ra.get_one(resource, _id)


@app.get("/portal/admin/{resource}")
async def get_list(
    request: Request,
    response: Response,
    resource: str,
    commons: dict = Depends(common_ra_parameters),
    _id: list[UUID] | None = Query(default=None, alias="id"),
):

    # Instansiate the kwargs object, incase no kwargs are passed
    kwargs = {}
    # Iterate through the query parameters
    for query, value in request.query_params.items():
        # Skip any that are in commons, as well as if they are "id"
        if query not in commons.keys() and query != "id":
            kwargs[query] = value
        # This can sometimes be a list of id's so we want to capture all of them in a list.
        elif query == "id":
            kwargs["id"] = _id

    # Get the entities and the count.
    entities, count = await ra.get_list(resource, commons, kwargs)

    # List responses require the count to be set in the header using a custom param.
    response.headers["X-Total-Count"] = count
    return entities


@app.put("/portal/admin/{resource}/{_id}", include_in_schema=False)
async def update(resource: str, _body: dict, _id: UUID):
    return await ra.update(resource, _body, _id)


@app.delete("/portal/admin/{resource}/{_id}", include_in_schema=False)
async def delete(resource: str, _id: UUID):
    return await ra.delete(resource, _id)


@app.delete("/portal/admin/{resource}", include_in_schema=False)
async def delete_many(
    resource: str, _ids: list[UUID] = Query(default=None, alias="ids")
):
    for _id in _ids:
        rows_deleted = await ra.delete(resource, _id)
    return {"message": f"Deleted {rows_deleted} rows."}


# How much should i spend today?
#   Get budget remaining for the month, divide by number of days remaining.
#   Might need to calculate average cost of nights out/takeaways etc if thinking of buying one

# On track
#   Something to give a good indication of whether i'm on track or not.

# TODO Look at bulk creating and updating to save DB calls.
# https://tortoise.github.io/setup.html?h=bulk#tortoise.Model.bulk_update.fields


@app.get("/budgets-needed")
async def budgets_needed():
    return await ynab.budgets_needed()


@app.get("/budgets-summary")
async def budgets_summary():
    return await ynab.budgets_summary()


@app.get("/categories-summary")
async def categories_summary(commons: dict = Depends(common_cc_parameters)):
    year = commons.get("year")
    months = commons.get("months")
    month = commons.get("month")
    return await ynab.categories_summary(year=year, months=months, specific_month=month)


@app.get("/categories-summary/{category_name}/{subcategory_name}")
async def category_summary(
    category_name: str,
    subcategory_name: str,
    commons: dict = Depends(common_cc_parameters),
):
    year = commons.get("year")
    months = commons.get("months")
    month = commons.get("month")

    return await ynab.category_summary(
        category_name=category_name,
        subcategory_name=subcategory_name,
        year=year,
        months=months,
        specific_month=month,
    )


@app.get("/daily-spend")
async def daily_spend(num_days: int):
    if num_days > 7:
        logging.warn("TODO - think about what to do here.")
        return None
    return await ynab.daily_spend(num_days=num_days)


@app.get("/direct-debits")
async def direct_debits():
    return await ynab.direct_debits()


@app.get("/insurance")
async def insurance():
    return await ynab.insurance()


@app.get("/loan-portfolio")
async def loan_portfolio():
    return await ynab.loan_portfolio()


@app.get("/monthly-summary")
async def monthly_summary(commons: dict = Depends(common_cc_parameters)):
    year = commons.get("year")
    months = commons.get("months")
    month = commons.get("month")
    return await ynab.month_summary(year=year, months=months, specific_month=month)


@app.get("/refunds")
async def refunds():
    return await ynab.refunds()


@app.get("/savings")
async def savings():
    return await ynab.savings(year=SpecificYearOptionsEnum.NOW)


@app.get("/transaction-summary")
async def transaction_summary(commons: dict = Depends(common_cc_parameters)):
    year = commons.get("year")
    months = commons.get("months")
    month = commons.get("month")
    return await ynab.transaction_summary(
        year=year, months=months, specific_month=month
    )


@app.get("/upcoming-bills")
async def upcoming_bills():
    return await ynab.upcoming_bills()


@app.get("/upcoming-bills/details")
async def upcoming_bills_details():
    return await ynab.upcoming_bills_details()


@app.get("/ynab/update-accounts", name="Update YNAB Accounts")
async def update_accounts():
    return await ynab_help.pydantic_accounts()


@app.get("/ynab/update-categories", name="Update YNAB Categories")
async def update_categories():
    return await ynab_help.pydantic_categories()


@app.get("/ynab/update-month-details", name="Update YNAB Month Details")
async def update_month_details():
    # Does previous month category summaries. Will only do previous months.
    return await ynab_help.pydantic_month_details()


@app.get("/ynab/update-month-summaries", name="Update YNAB Month Summaries")
async def update_month_summaries():
    # Does the current year summaries
    return await ynab_help.pydantic_month_summaries()


@app.get("/ynab/update-payees", name="Update YNAB Payees")
async def update_payees():
    return await ynab_help.pydantic_payees()


@app.get("/ynab/update-savings", name="Update Savings Outcomes")
async def update_savings(commons: dict = Depends(common_cc_parameters)):
    year = commons.get("year")
    month = commons.get("month")

    if not year or not month:
        year = SpecificYearOptionsEnum.NOW
        month = SpecificMonthOptionsEnum.NOW
    else:
        year = SpecificYearOptionsEnum(year)
        month = SpecificMonthOptionsEnum(month)

    entities, count = await ra.get_list(
        resource="savings",
        commons={"_end": 1, "_start": 0, "_order": "ASC", "_sort": "date"},
        kwargs_raw={
            "date__month": month.value,
            "date__year": year.value,
            "name": "Monthly",
        },
    )

    if int(count) < 1:
        return {"message": "No savings target available for update."}

    month_savings = await ynab.month_savings(year=year, specific_month=month)

    savings_entity = entities[0]
    savings_entity_id = str(savings_entity.id)
    savings_entity.amount = month_savings.total
    savings_entity.date = datetime.strftime(savings_entity.date, "%Y-%m-%d")
    logging.debug(f"Entity updated to update savings target: {savings_entity}")

    update_dict = savings_entity.__dict__
    update_dict.pop("id")
    logging.debug(f"Dict created to allow for db save: {update_dict}")

    return await update(resource="savings", _body=update_dict, _id=savings_entity_id)


@app.get("/ynab/update-transactions", name="Update YNAB Transactions")
async def update_transactions():
    await ynab_help.pydantic_transactions()
    # Below needs categories to exist.
    return await ynab_help.sync_transaction_rels()


@app.get("/ynab/update-transaction-rels", name="Update YNAB Transaction Relations")
async def update_transaction_rels():
    return await ynab_help.sync_transaction_rels()


@app.get("/test/endpoint")
async def test_get_endpoint(commons: dict = Depends(common_cc_parameters)):
    year = commons.get("year")
    months = commons.get("months")
    month = commons.get("month")

    start_date, end_date = await ynab_help.get_dates_for_transaction_queries(
        year=year, months=months, specific_month=month
    )
    return await ynab.test_endpoint(specific_month=month, year=year)


@app.post("/test/endpoint/{resource}", include_in_schema=False)
async def test_post_endpoint(resource: str, _body: dict):
    logging.info(resource)
    logging.error(_body)
    return {"message": "done"}


@app.route("/{path:path}")
def catch_all(path: str):
    logging.warning(f"Resource attempted by {path.headers}")
    raise HTTPException(status_code=404, detail="Not Found")
