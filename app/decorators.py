import logging

def protected_endpoint(func):
    def wrap(*args, **kwargs):
        logging.info(f"Calling {func.__name__} with args: {args}, kwargs: {kwargs}")
        func()
    return wrap
