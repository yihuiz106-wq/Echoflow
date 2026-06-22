from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

TRANSIENT_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
}


def is_transient_api_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return True

    name = error.__class__.__name__
    if name in TRANSIENT_ERROR_NAMES:
        return True

    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "timeout",
            "timed out",
            "connection error",
            "connection reset",
            "temporarily unavailable",
        )
    )


def call_with_retry(operation: Callable[[], T], *, attempts: int = 2) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt >= attempts - 1 or not is_transient_api_error(error):
                raise

    raise last_error if last_error else RuntimeError("retry failed without an error")
