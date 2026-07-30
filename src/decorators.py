import inspect
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, TypeVar

from src.config import _IN_PRODUCTION, log

F = TypeVar("F", bound=Callable[..., Any])


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


def skip_if_reason(reasons: Sequence[str], *, param: str = "reason") -> Callable[[F], F]:
    """Skip the decorated function when its reason argument is in `reasons`."""
    skip_reasons = frozenset(reasons)

    def decorator(func: F) -> F:
        # Capture parameter names/order so we can read `reason` from *args/**kwargs.
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            reason_value = bound.arguments.get(param)

            if reason_value in skip_reasons:
                # log.warning(
                    # f"Skipping function {func.__name__} because {param}={reason_value!r} "
                    # f"is in the skip list."
                # )
                return None
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
