from functools import wraps

from src.config import _IN_PRODUCTION, log


def production_only(func):
    """
    A decorator to ensure that a function is only executed when the application is in production.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if _IN_PRODUCTION:
            return func(*args, **kwargs)
        else:
            log.warning(f"Skipping function {func.__name__} because it is not in production.")
            return None
    return wrapper
