import os
import json
import logging
import sys
from tortoise import Tortoise
from dotenv import load_dotenv, dotenv_values
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Depends, Query, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from uuid import UUID
from app.db.helpers import ReactAdmin as ra

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(filename)s %(asctime)s %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    dotenv_db_url = os.getenv("DB_URL")
    logging.info("Initialising DB")
    await Tortoise.init(
        db_url=dotenv_db_url,
        modules={'models': ['app.db.models']},
    )
    # Generate the model schemas.
    logging.info("Generating Schemas")
    await Tortoise.generate_schemas()
    yield
    logging.info("Shutting down application.")
    # Close all connections when shutting down.
    await Tortoise.close_connections()

config = dotenv_values(".env")

dotenv_token = config["ENV_TOKEN"]
dotenv_hosts = json.loads(config["ENV_HOSTS"])
dotenv_origins = json.loads(config["ENV_ORIGINS"])
dotenv_docs = config["ENV_DOCS"] if config["ENV_DOCS"] != 'None' else None

async def get_token_header(request: Request, x_token: str = Header(...)):
    if dotenv_origins != ['*'] or dotenv_hosts != ['*']:
        try:
            origin = request.headers["origin"]
            referer = request.headers["referer"]
            if referer not in dotenv_origins or origin not in dotenv_hosts:
                logging.warning(f"Origin {origin} attempted access using a valid token to {origin}.")
                raise HTTPException(status_code=403)
        except KeyError:
            logging.warning("Attempt to access API from unauthorised location.")
            raise HTTPException(status_code=403)

        if x_token != dotenv_token:
            logging.warning(f"Origin {referer} provided an invalid token.")
            raise HTTPException(status_code=403)

app = FastAPI(
    lifespan=lifespan,
    dependencies=[Depends(get_token_header)],
    openapi_url=dotenv_docs
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=dotenv_origins,
    expose_headers=['x-total-count'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=['Content-Type', 'User-Agent', 'x-token', 'Referer', 'Origin']
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=dotenv_hosts
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
        await ra.delete(resource, _id)
    return #add log here to say done or something


@app.post("/ext/transactions", status_code=201)
async def create_transaction(_body: dict):
    return await ra.create("transactions", _body)

# Add specific endpoints for getting rechart data. e.g. /rechart/{resource}
# Always has to be returned as follows
# List[Object]
# Object = key, value pairs
# { "name": "a", "metric1": "value1", etc... }

@app.get("/dashboard/direct-debits/total")
async def get_dd_totals():
    entity_model = await ra.get_entity_model('direct-debits')
    entity_schema = await ra.get_entity_schema('direct-debits')

    db_entities = await entity_schema.from_queryset(entity_model.filter(period="monthly"))

    monthly_total = 0
    annual_total = 0

    cost_breakdown = []

    for entity in db_entities:
        cost_breakdown.append({
            "name": entity.name,
            "company": entity.company.name,
            "amount": entity.amount
        })
        monthly_total += entity.amount
        annual_total += entity.annual_cost

    return {
        "data": cost_breakdown,
        "monthly_total": monthly_total,
        "annual_total": annual_total
    }

# Upcoming payments endpoint
# Shows the next 3 days worth of payments
# Can show more if needed
