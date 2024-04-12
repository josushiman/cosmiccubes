import logging
import newrelic.agent
from time import sleep
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tortoise import Tortoise
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Depends, Query, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
from app.config import settings
from app.reactadmin.helpers import ReactAdmin as ra
from app.enums import PeriodOptions, PeriodMonthOptions, SpecificMonthOptions, SpecificYearOptions
from app.ynab.main import YNAB as ynab
from app.ynab.helpers import YnabHelpers as ynab_help
from app.decorators import protected_endpoint
from app.db.models import YnabTransactions

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
async def update_ynab_data():
    # Check YNAB is alive
    # Update each one in a loop, error out when something happens
    endpoints = [
        update_accounts,
        update_categories,
        update_payees,
        update_month_details,
        update_month_summaries,
        update_transactions
    ]

    for endpoint in endpoints:
        try:
            await endpoint(settings.ynab_phrase)
            sleep(seconds=60)
        except:
            logging.error(f"issue updating endpoint {endpoint}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initialising DB")
    await Tortoise.init(
        db_url=settings.db_url,
        modules={'models': ['app.db.models']},
    )
    # Generate the model schemas.
    logging.info("Generating schemas.")
    await Tortoise.generate_schemas()
    logging.info("Schemas generated.")
    logging.info("Starting scheduler.")
    # scheduler.add_job(update_ynab_data, trigger="cron", second=10)
    scheduler.start()
    yield
    # Close all connections when shutting down.
    logging.info("Shutting down scheduler.")
    scheduler.shutdown()
    logging.info("Shutting down application.")
    await Tortoise.close_connections()

async def get_token_header(request: Request, x_token: UUID = Header(...)):
    if dotenv_origins != ['*'] or dotenv_hosts != ['*']:
        logging.debug(request.headers.raw)
        try:
            referer = request.headers["referer"]
            host = request.headers["host"]
            if referer != dotenv_referer:
                logging.debug(f"Referer: {referer}")
                logging.warning(f"Referer {referer} attempted access using a valid token")
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
            user_agent = request.headers['user-agent']
            if user_agent != dotenv_user_agent:
                logging.warning(f"Origin was not set for {request.headers['host']} on IP: {request.headers['true-client-ip']}. User Agent string: {user_agent}")

    if x_token != dotenv_token:
        logging.warning(f"Invalid token provided from Origin and/or Host")
        raise HTTPException(status_code=403)

logging.debug(f"{dotenv_docs}")
logging.debug(f"{dotenv_hosts}, {dotenv_origins}, {dotenv_referer}")

app = FastAPI(
    lifespan=lifespan,
    dependencies=[Depends(get_token_header)],
    openapi_url=dotenv_docs
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[dotenv_origins],
    expose_headers=['x-total-count'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

async def common_ra_parameters(
        _end: int = 10,
        _start: int = 0,
        _order: str = Query(default="ASC", min_length=3, max_length=4, regex="ASC|DESC"),
        _sort: str = None
    ):
    return {"_end": _end, "_start": _start, "_order": _order, "_sort": _sort}

async def common_cc_parameters(
        year: SpecificYearOptions = None,
        months: PeriodMonthOptions = None,
        month: SpecificMonthOptions = None
    ):
    return {"year": year, "months": months, "month": month}

@app.get("/health", status_code=200)
async def get_health():
    return {
        "status": "OK"
    }

@app.post("/portal/admin/{resource}", status_code=201, include_in_schema=False)
async def create(resource: str, _body: dict):
    return await ra.create(resource, _body)

@app.get("/portal/admin/{resource}/{_id}", include_in_schema=False)
async def get_one(resource: str, _id: UUID):
    return await ra.get_one(resource, _id)

@app.get("/portal/admin/{resource}", include_in_schema=False)
async def get_list(request: Request, response: Response, resource: str, commons: dict = Depends(common_ra_parameters), \
    _id: list[UUID] | None = Query(default=None, alias="id")):
    
    # Instansiate the kwargs object, incase no kwargs are passed
    kwargs = {}
    # Iterate through the query parameters
    for query, value in request.query_params.items():
        # Skip any that are in commons, as well as if they are "id"
        if query not in commons.keys() and query != 'id':
            kwargs[query] = value
        # This can sometimes be a list of id's so we want to capture all of them in a list.
        elif query == 'id':
            kwargs['id'] = _id

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
async def delete_many(resource: str, _ids: list[UUID] = Query(default=None, alias="ids")):
    for _id in _ids:
        rows_deleted = await ra.delete(resource, _id)
    return {
        "message": f"Deleted {rows_deleted} rows."
    }

# How much should i spend today?
#   Get budget remaining for the month, divide by number of days remaining.
#   Might need to calculate average cost of nights out/takeaways etc if thinking of buying one

# On track
#   Something to give a good indication of whether i'm on track or not.

# TODO Look at bulk creating and updating to save DB calls
# https://tortoise.github.io/setup.html?h=bulk#tortoise.Model.bulk_update.fields

@app.get("/ynab/categories-summary")
async def categories_summary(commons: dict = Depends(common_cc_parameters)):
    year = commons.get('year')
    months = commons.get('months')
    month = commons.get('month')
    return await ynab.categories_summary(year=year, months=months, specific_month=month)

@app.get("/ynab/monthly-summary")
async def monthly_summary(commons: dict = Depends(common_cc_parameters)):
    year = commons.get('year')
    months = commons.get('months')
    month = commons.get('month')
    return await ynab.month_summary(year=year, months=months, specific_month=month)

@app.get("/ynab/transaction-summary")
async def monthly_summary(commons: dict = Depends(common_cc_parameters)):
    year = commons.get('year')
    months = commons.get('months')
    month = commons.get('month')
    return await ynab.transaction_summary(year=year, months=months, specific_month=month)

@app.get("/ynab/available-balance")
async def available_balance():
    return await ynab.available_balance()

@app.get("/ynab/card-balances")
async def card_balances(commons: dict = Depends(common_cc_parameters)):
    return await ynab.card_balances(year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/categories-spent")
async def categories_spent(commons: dict = Depends(common_cc_parameters)):
    return await ynab.categories_spent(year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/earned-vs-spent")
async def earned_vs_spent(commons: dict = Depends(common_cc_parameters)):
    return await ynab.earned_vs_spent(year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/income-vs-expenses")
async def income_vs_expenses(commons: dict = Depends(common_cc_parameters)):
    return await ynab.income_vs_expenses(year=commons['year'], months=commons['months'], specific_month=commons['month'])

#TODO include amounts for the last paid dates. Accumulate if you received multiple in the same month.
@app.get("/ynab/last-paid-date-for-accounts")
async def last_paid_date_for_accounts(commons: dict = Depends(common_cc_parameters)):
    return await ynab.last_paid_date_for_accounts(year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/last-x-transactions")
async def last_x_transactions(count: int, commons: dict = Depends(common_cc_parameters)):
    return await ynab.last_x_transactions(count, year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/spent-in-period")
async def spent_in_period(period: PeriodOptions):
    return await ynab.spent_in_period(period)

@app.get("/ynab/spent-vs-budget")
async def spent_vs_budget(commons: dict = Depends(common_cc_parameters)):
    return await ynab.spent_vs_budget(year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/sub-categories-spent")
async def sub_categories_spent(commons: dict = Depends(common_cc_parameters)):
    return await ynab.sub_categories_spent(year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/total-spent")
async def total_spent(commons: dict = Depends(common_cc_parameters)):
    return await ynab.total_spent(year=commons['year'], months=commons['months'], specific_month=commons['month'])

@app.get("/ynab/transaction-by-month-for-year")
async def transactions_by_month_for_year(year: SpecificYearOptions):
    return await ynab.transactions_by_month_for_year(year)

@app.get("/ynab/transaction-by-months")
async def transactions_by_months(months: PeriodMonthOptions):
    return await ynab.transactions_by_months(months)

@app.get("/ynab/update-accounts", name="Update YNAB Accounts")
@protected_endpoint
async def update_accounts():
    return await ynab_help.pydantic_accounts()

@app.get("/ynab/update-categories", name="Update YNAB Categories")
@protected_endpoint
async def update_categories():
    return await ynab_help.pydantic_categories()

@app.get("/ynab/update-month-details", name="Update YNAB Month Details")
@protected_endpoint
async def update_month_details():
    # Does previous month category summaries. Will only do previous months.
    return await ynab_help.pydantic_month_details()

@app.get("/ynab/update-month-summaries", name="Update YNAB Month Summaries")
@protected_endpoint
async def update_month_summaries():
    # Does the current year summaries
    return await ynab_help.pydantic_month_summaries()

@app.get("/ynab/update-payees", name="Update YNAB Payees")
@protected_endpoint
async def update_payees():
    return await ynab_help.pydantic_payees()

@app.get("/ynab/update-transactions", name="Update YNAB Transactions")
@protected_endpoint
async def update_transactions():
    await ynab_help.pydantic_transactions()
    # Below needs categories to exist.
    return await ynab_help.sync_transaction_rels()

@app.get("/ynab/update-transaction-rels", name="Update YNAB Transaction Relations")
@protected_endpoint
async def update_transaction_rels():
    return await ynab_help.sync_transaction_rels()

@app.get("/test/endpoint")
async def test_endpoint():
    return await ynab.transaction_summary()
    return await YnabTransactions.filter(category_fk_id=None, transfer_account_id=None).count()

@app.route("/{path:path}")
def catch_all(path: str):
    logging.warning(f"Resource attempted by {path.headers}")
    raise HTTPException(status_code=404, detail="Not Found")
