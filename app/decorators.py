import logging
from fastapi import HTTPException
from app.config import settings

# 'func' is the function you are wrapping
def protected_endpoint(func):
    # This needs to be async as FastAPI endpoints are async.
    # 'phrase' being set here forces the wrapped function to provide that value as a param.
    async def check_ynab_phrase(phrase: str):
        logging.info(f"Calling {func.__name__}")
        if phrase != settings.ynab_phrase:
            raise HTTPException(status_code=403, detail="Not authorised")
        # You need to ensure you return AND await the function you're wrapping.
        # Otherwise it won't be awaited and will likely return 'null'
        return await func()
    return check_ynab_phrase

# TODO is this even possible?
def unpack_cc_commons(func):
    async def process_varaibles(commons_dict):
        year = commons_dict.get('year')
        months = commons_dict.get('months')
        month = commons_dict.get('month')
        return await func()
    return process_varaibles

# TODO
def log_sql_query(func):
    async def check_sql(queryset):
        return await func()
    return log_sql_query