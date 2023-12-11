import os
from tortoise import Tortoise
from dotenv import load_dotenv
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
from app.helpers import ReactAdmin as ra

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    dotenv_db_url = os.getenv("DB_URL")
    await Tortoise.init(
        db_url=dotenv_db_url,
        modules={'models': ['app.models']},
    )
    # Generate the model schemas.
    await Tortoise.generate_schemas()
    yield
    # Close all connections when shutting down.
    await Tortoise.close_connections()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    expose_headers=['x-total-count'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def common_parameters(_end: int = 10, _start: int = 0, _order: str = Query(default="ASC", min_length=3, max_length=4, regex="ASC|DESC"), \
    _sort: str = None):
    return {"_end": _end, "_start": _start, "_order": _order, "_sort": _sort}

@app.post("/{resource}", status_code=201)
async def create(resource: str, _body: dict):
    return await ra.create(resource, _body)

@app.get("/{resource}/{_id}")
async def get_one(resource: str, _id: UUID):
    return await ra.get_one(resource, _id)

@app.get("/{resource}")
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

@app.put("/{resource}/{_id}")
async def update(resource: str, _body: dict, _id: UUID):
    return await ra.update(resource, _body, _id)

@app.delete("/{resource}/{_id}", status_code=204)
async def delete(resource: str, _id: UUID):
    return await ra.delete(resource, _id)

@app.delete("/{resource}", status_code=204)
async def delete_many(resource: str, _ids: list[UUID] = Query(default=None, alias="ids")):
    for _id in _ids:
        await ra.delete(resource, _id)
    return #add log here to say done or something
