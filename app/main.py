import os
import logging
import json
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
from app.db.models import YnabServerKnowledge
from app.enums import FilterTypes, PeriodOptions, PeriodMonthOptions, SpecificMonthOptions, SpecificYearOptions, TopXOptions, \
    TransactionTypeOptions

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

@app.post("/portal/admin/{resource}", status_code=201)
async def create(resource: str, _body: dict):
    return await ra.create(resource, _body)

@app.get("/portal/admin/{resource}/{_id}")
async def get_one(resource: str, _id: UUID):
    return await ra.get_one(resource, _id)

@app.get("/portal/admin/{resource}")
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

@app.put("/portal/admin/{resource}/{_id}")
async def update(resource: str, _body: dict, _id: UUID):
    return await ra.update(resource, _body, _id)

@app.delete("/portal/admin/{resource}/{_id}")
async def delete(resource: str, _id: UUID):
    return await ra.delete(resource, _id)

@app.delete("/portal/admin/{resource}")
async def delete_many(resource: str, _ids: list[UUID] = Query(default=None, alias="ids")):
    for _id in _ids:
        rows_deleted = await ra.delete(resource, _id)
    return {
        "message": f"Deleted {rows_deleted} rows."
    }

@app.get("/portal/admin/dashboard/direct-debits/{type}")
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

@app.get("/ynab/spent-vs-budget")
async def spent_vs_budget():
    return await ynab.spent_vs_budget()

@app.get("/ynab/sub-categories-spent")
async def sub_categories_spent(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.sub_categories_spent(year=year, months=months, specific_month=month)

@app.get("/ynab/last-x-transactions")
async def last_x_transactions(count: int, since_date: str = None):
    return await ynab.last_x_transactions(count, since_date)

@app.get("/ynab/income-vs-expenses")
async def income_vs_expenses(year: SpecificYearOptions = None, months: PeriodMonthOptions = None, month: SpecificMonthOptions = None):
    return await ynab.income_vs_expenses(year=year, months=months, specific_month=month)

@app.get("/ynab/last-paid-date-for-accounts")
async def last_paid_date_for_accounts():
    return await ynab.last_paid_date_for_accounts(months=PeriodMonthOptions.MONTHS_1)

@app.get("/ynab/spent-in-period")
async def spent_in_period(period: PeriodOptions):
    return await ynab.spent_in_period(period)

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
    # TODO setup a cron job on the server to run this on a daily basis.
    # Check last server knowledge of route
    route_url = "/budgets/e473536e-1a6c-42b1-8c90-c780a36b5580/transactions"
    db_entity = await YnabServerKnowledge.get_or_none(route=route_url)

    if db_entity:
        server_knowledge = db_entity.server_knowledge        
        transaction_list = await ynab.make_request(action='transactions-list', param_1="e473536e-1a6c-42b1-8c90-c780a36b5580", param_2=server_knowledge)
    else:
        server_knowledge = None
        transaction_list = await ynab.make_request(action='transactions-list', param_1="e473536e-1a6c-42b1-8c90-c780a36b5580")

    pydantic_transactions_list = TransactionsResponse.model_validate_json(json.dumps(transaction_list))
    if server_knowledge == pydantic_transactions_list.data.server_knowledge or len(pydantic_transactions_list.data.transactions) == 0:
        return { "message": "No new transactions to store or update."}

    for transaction in pydantic_transactions_list.data.transactions:
        if transaction.deleted: continue
        model_dict = transaction.model_dump()
        model_dict.pop("subtransactions")
        await ra.create_or_update(resource="ynab-transaction", resp_body=model_dict, _id=transaction.id)

    server_knowledge_body = {
        "budget_id": "e473536e-1a6c-42b1-8c90-c780a36b5580",
        "route": "/budgets/e473536e-1a6c-42b1-8c90-c780a36b5580/transactions",
        "server_knowledge": pydantic_transactions_list.data.server_knowledge
    }

    return await ra.create_or_update(resource="ynab-server-knowledge", resp_body=server_knowledge_body, _id="de596c1a-6e4a-44d6-84c5-716e50e18e03")
