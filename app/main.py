import logging
import newrelic.agent
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

dotenv_token = settings.env_token
dotenv_hosts = settings.env_hosts
dotenv_origins = settings.env_origins
dotenv_referer = settings.env_referer
dotenv_docs = settings.env_docs
dotenv_path_to_ini = settings.newrelic_ini_path

logging.info("Initialising NewRelic")
newrelic.agent.initialize(dotenv_path_to_ini, settings.newrelic_env)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initialising DB")
    await Tortoise.init(
        db_url=settings.db_url,
        modules={'models': ['app.db.models']},
    )
    # Generate the model schemas.
    logging.info("Generating Schemas")
    await Tortoise.generate_schemas()
    logging.info("Schemas Generated")
    yield
    # Close all connections when shutting down.
    logging.info("Shutting down application.")
    await Tortoise.close_connections()

async def get_token_header(request: Request, x_token: str = Header(...)):
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
            logging.warning(f"Origin was not set for {request.headers['host']} on IP: {request.headers['true-client-ip']}. User Agent string: {request.headers['user-agent']}")

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

async def common_parameters(_end: int = 10, _start: int = 0, _order: str = Query(default="ASC", min_length=3, max_length=4, regex="ASC|DESC"), \
    _sort: str = None):
    return {"_end": _end, "_start": _start, "_order": _order, "_sort": _sort}

@app.get("/health")
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
async def get_list(request: Request, response: Response, resource: str, commons: dict = Depends(common_parameters), \
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

@app.get("/ynab/available-balance")
async def available_balance():
    return await ynab.available_balance()

@app.get("/ynab/card-balances")
async def card_balances():
    return await ynab.card_balances()

@app.get("/ynab/categories-spent")
async def categories_spent(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.categories_spent(year=year, months=months, specific_month=month)

@app.get("/ynab/earned-vs-spent")
async def earned_vs_spent(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.earned_vs_spent(year=year, months=months, specific_month=month)

@app.get("/ynab/income-vs-expenses")
async def income_vs_expenses(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.income_vs_expenses(year=year, months=months, specific_month=month)

@app.get("/ynab/last-paid-date-for-accounts")
async def last_paid_date_for_accounts(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.last_paid_date_for_accounts(year=year, months=months, specific_month=month)

@app.get("/ynab/last-x-transactions")
async def last_x_transactions(count: int, year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.last_x_transactions(count, year=year, months=months, specific_month=month)

@app.get("/ynab/spent-in-period")
async def spent_in_period(period: PeriodOptions):
    return await ynab.spent_in_period(period)

@app.get("/ynab/spent-vs-budget")
async def spent_vs_budget(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.spent_vs_budget(year=year, months=months, specific_month=month)

@app.get("/ynab/sub-categories-spent")
async def sub_categories_spent(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.sub_categories_spent(year=year, months=months, specific_month=month)

@app.get("/ynab/total-spent")
async def total_spent(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.total_spent(year=year, months=months, specific_month=month)

@app.get("/ynab/transaction-by-month-for-year")
async def transactions_by_month_for_year(year: SpecificYearOptions):
    return await ynab.transactions_by_month_for_year(year)

@app.get("/ynab/transaction-by-months")
async def transactions_by_months(months: PeriodMonthOptions):
    return await ynab.transactions_by_months(months)

# TODO make this a decorator
async def check_ynab_phrase(phrase: str) -> bool | HTTPException:
    if phrase != settings.ynab_phrase:
        raise HTTPException(status_code=403, detail="Not authorised")
    return True

@app.get("/ynab/update-accounts")
async def update_accounts(phrase: str):
    await check_ynab_phrase(phrase=phrase)
    return await ynab_help.pydantic_accounts()

@app.get("/ynab/update-categories")
async def update_categories(phrase: str):
    await check_ynab_phrase(phrase=phrase)
    return await ynab_help.pydantic_categories()

@app.get("/ynab/update-month-details")
async def update_month_details(phrase: str):
    await check_ynab_phrase(phrase=phrase)
    # Does previous month category summaries. Will only do previous months.
    return await ynab_help.pydantic_month_details()

@app.get("/ynab/update-month-summaries")
async def update_month_summaries(phrase: str):
    await check_ynab_phrase(phrase=phrase)
    # Does the current year summaries
    return await ynab_help.pydantic_month_summaries()

@app.get("/ynab/update-payees")
async def update_payees(phrase: str):
    await check_ynab_phrase(phrase=phrase)
    return await ynab_help.pydantic_payees()

@app.get("/ynab/update-transactions")
async def update_transactions(phrase: str):
    await check_ynab_phrase(phrase=phrase)
    await ynab_help.pydantic_transactions()
    # Below needs categories to exist.
    return await ynab_help.sync_transaction_rels()

@app.route("/{path:path}")
def catch_all(path: str):
    logging.warning(f"Resource attempted by {path.headers}")
    raise HTTPException(status_code=404, detail="Not Found")
