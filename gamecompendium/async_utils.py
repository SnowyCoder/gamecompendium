from typing import TypeVar, Awaitable
import traceback

T = TypeVar('T')


async def soft_log_exceptions(wrapped: Awaitable[T]) -> T:
    try:
        return await wrapped
    except Exception:
        print(f"Oops, exception occurred!")
        traceback.print_exc()

