import logging
from fastapi import HTTPException
from app.config import settings

def protected_endpoint(func):
    async def check_ynab_phrase(phrase: str):
        logging.debug(f"Calling {func.__name__} with args: {phrase}")
        if phrase != settings.ynab_phrase:
            raise HTTPException(status_code=403, detail="Not authorised")
        return await func()
    return check_ynab_phrase
