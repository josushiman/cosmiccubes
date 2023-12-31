import os
import logging
import json
from enum import Enum, IntEnum
from tortoise import Tortoise
from dotenv import load_dotenv
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Depends, Query, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
from app.db.helpers import ReactAdmin as ra
from app.ynab import YNAB as ynab
from app.ynab_models import TransactionsResponse
from app.db.models import YnabServerKnowledge, YnabTransactions
from app.db.schemas import YnabServerKnowledge_Pydantic

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(filename)s %(asctime)s %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

load_dotenv()
dotenv_db_url = os.getenv("DB_URL")
dotenv_token = os.getenv("ENV_TOKEN")
raw_hosts = os.getenv("ENV_HOSTS")
raw_origins = os.getenv("ENV_ORIGINS")
raw_referer = os.getenv("ENV_REFERER")
raw_docs = os.getenv("ENV_DOCS")
dotenv_hosts = raw_hosts if raw_hosts != 'None' else ["*"]
dotenv_origins = raw_origins if raw_origins != 'None' else ["*"]
dotenv_referer = raw_referer if raw_referer != 'None' else ["*"]
dotenv_docs = raw_docs if raw_docs != 'None' else None

logging.debug(f"{dotenv_hosts}, {dotenv_origins}, {dotenv_referer}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initialising DB")
    await Tortoise.init(
        db_url=dotenv_db_url,
        modules={'models': ['app.db.models']},
    )
    # Generate the model schemas.
    logging.info("Generating Schemas")
    await Tortoise.generate_schemas()
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

@app.post("/portal/{resource}", status_code=201)
async def create(resource: str, _body: dict):
    return await ra.create(resource, _body)

@app.get("/portal/{resource}/{_id}")
async def get_one(resource: str, _id: UUID):
    return await ra.get_one(resource, _id)

@app.get("/portal/{resource}")
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

@app.put("/portal/{resource}/{_id}")
async def update(resource: str, _body: dict, _id: UUID):
    return await ra.update(resource, _body, _id)

@app.delete("/portal/{resource}/{_id}")
async def delete(resource: str, _id: UUID):
    return await ra.delete(resource, _id)

@app.delete("/portal/{resource}")
async def delete_many(resource: str, _ids: list[UUID] = Query(default=None, alias="ids")):
    for _id in _ids:
        rows_deleted = await ra.delete(resource, _id)
    return {
        "message": f"Deleted {rows_deleted} rows."
    }

@app.get("/portal/dashboard/direct-debits/{type}")
async def get_dd_totals(type: str):
    entity_model = await ra.get_entity_model('direct-debits')
    entity_schema = await ra.get_entity_schema('direct-debits')

    db_entities = await entity_schema.from_queryset(entity_model.all())

    monthly_total = 0
    annual_total = 0

    for entity in db_entities:
        if entity.period == "monthly":
            monthly_total += entity.amount
        annual_total += entity.annual_cost

    return {
        "monthly_total": monthly_total,
        "annual_total": annual_total
    }

class FilterTypes(Enum):
    ACCOUNT = 'account'
    CATEGORY = 'category'
    PAYEE = 'payee'

class PeriodMonthOptions(IntEnum):
    MONTHS_1 = 1
    MONTHS_3 = 3
    MONthS_6 = 6
    MONTHS_9 = 9
    MONTHS_12 = 12

class SpecificMonthOptions(Enum):
    JANUARY = '01'
    FEBRUARY = '02'
    MARCH = '03'
    APRIL = '04'
    MAY = '05'
    JUNE = '06'
    JULY = '07'
    AUGUST = '08'
    SEPTEMBER = '09'
    OCTOBER = '10'
    NOVEMBER = '11'
    DECEMBER = '12'

class SpecificYearOptions(Enum):
    YEAR_23 = '2023'
    YEAR_24 = '2024'
    YEAR_25 = '2025'

class TopXOptions(IntEnum):
    TOP_3 = 3
    TOP_5 = 5
    TOP_10 = 10

class TransactionTypeOptions(Enum):
    INCOME = 'income'
    EXPENSES = 'expenses'

@app.get("/ynab/available-balance")
async def get_available_balance():
    return await ynab.get_available_balance()

@app.get("/ynab/card-balances")
async def get_card_balances():
    return await ynab.get_card_balances()

@app.get("/ynab/category-summary")
async def get_category_summary():
    return await ynab.get_category_summary()

@app.get("/ynab/last-paid-date-for-accounts")
async def last_paid_date_for_accounts():
    return await ynab.last_paid_date_for_accounts(months=PeriodMonthOptions.MONTHS_1)

@app.get("/ynab/last-x-transactions")
async def get_last_x_transactions(count: int, since_date: str = None):
    return await ynab.get_last_x_transactions(count, since_date)

@app.get("/ynab/totals")
async def get_totals(transaction_type: TransactionTypeOptions, year: SpecificYearOptions = None, months: PeriodMonthOptions = None, \
    specific_month: SpecificMonthOptions = None):
    return await ynab.get_totals(
        transaction_type=transaction_type,
        filter_type=FilterTypes.ACCOUNT,
        year=year,
        months=months,
        specific_month=specific_month,
    )

@app.get("/ynab/transaction-by-month-for-year")
async def get_transactions_by_month_for_year(year: SpecificYearOptions):
    return await ynab.transactions_by_month_for_year(year)

@app.get("/ynab/transaction-by-months")
async def get_transactions_by_months(months: PeriodMonthOptions):
    return await ynab.transactions_by_months(months)

@app.get("/ynab/transactions-by-filter-type")
async def get_transactions_by_filter_type(filter_type: FilterTypes, transaction_type: TransactionTypeOptions, \
    year: SpecificYearOptions = None, top_x: TopXOptions = None, months: PeriodMonthOptions = None, specific_month: SpecificMonthOptions = None):
    return await ynab.transactions_by_filter_type(
        transaction_type=transaction_type,
        filter_type=filter_type,
        year=year,
        months=months,
        specific_month=specific_month,
        top_x=top_x,
    )

@app.get("/ynab/latest-transactions")
async def get_latest_transactions():
    # Check last server knowledge of route
    route_url = "/budgets/25c0c5c4-98fa-452c-9d31-ee3eaa50e1b2/transactions"
    db_entity = await YnabServerKnowledge.get_or_none(route=route_url)

    if db_entity:
        server_knowledge = db_entity.server_knowledge        
        transaction_list = await ynab.make_request(action='transactions-list', param_1="25c0c5c4-98fa-452c-9d31-ee3eaa50e1b2", param_2=server_knowledge)
    else:
        transaction_list = await ynab.make_request(action='transactions-list', param_1="25c0c5c4-98fa-452c-9d31-ee3eaa50e1b2")

    pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))
    if server_knowledge == pydantic_transactions_list.data.server_knowledge or len(pydantic_transactions_list.data.transactions) == 0:
        return { "message": "No new transactions to store."}

    for transaction in pydantic_transactions_list.data.transactions:
        await ra.create(resource="ynab-transaction", resp_body=transaction.model_dump())

    server_knowledge_body = {
        "budget_id": "25c0c5c4-98fa-452c-9d31-ee3eaa50e1b2",
        "route": "/budgets/25c0c5c4-98fa-452c-9d31-ee3eaa50e1b2/transactions",
        "server_knowledge": pydantic_transactions_list.data.server_knowledge
    }

    return await ra.create(resource="ynab-server-knowledge", resp_body=server_knowledge_body)
