import asyncio
from typing import TypeVar, Awaitable, Callable

T = TypeVar('T')


class RateLimitExceedException(Exception):
    pass

# Internal design:
# All requests are put in a common queue,
# a middleware consumer runs at the specified rate and, at each tick, removes one item
# from the common queue and puts it in the rate-limited queue.
# multiple final consumers (number = to the max concurrent tasks available) pop a task from the
# rate limited queue and execute it


class RateLimiter:
    """
    Rate-limits async queries and implements retrial mechanisms appropriate for a robust scraping system

    Lots of APIs have rate limits on the number of queries that can be executed that are hard to maintain in
    asynchronous contexts, this class implements a limiting valve that, given multiple queries, executes them
    at the specified rate (with a specified maximum number. of concurrent queries).
    Another useful aspect is query re-execution, if the query surpassed rate limits the task can throw
    RateLimitExceedException, it will automatically be re-tried after some time (using exponential back-off).
    """

    def __init__(self, tasks_per_seconds: int, max_tasks_at_once: int):
        self._tasks_per_second = tasks_per_seconds
        self._queue = asyncio.Queue()
        self._rate_limited_queue = asyncio.Queue(1)
        self._consumers = [asyncio.create_task(self._consumer()) for _ in range(max_tasks_at_once)]
        self._producer_task = asyncio.create_task(self._producer())

    async def _producer(self):
        while True:
            x = await self._queue.get()
            await self._rate_limited_queue.put(x)
            await asyncio.sleep(1 / self._tasks_per_second)

            self._queue.task_done()

    async def _consumer(self):
        while True:
            x = await self._rate_limited_queue.get()
            await x
            self._rate_limited_queue.task_done()

    async def execute(self, x: Callable[[], Awaitable[T]]) -> T:
        """
        Inserts a task in the system, it will be executed at the specified rate

        Since the task can be restarted if a RateLimitExceedException is thrown the argument is not an awaitable
        but a task factory, that should produce a task each time it's called.

        :param x: A task factory
        :return: The returned result (once completed)
        """
        future = asyncio.Future()

        async def wrapper():
            retry = 0
            while True:
                try:
                    future.set_result(await x())
                    break
                except RateLimitExceedException:
                    retry += 1
                    # Exponential backoff
                    wait_time = 2+2**retry
                    print(f"Rate limit exceed, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    # Don't break: repeat
                except Exception as e:
                    future.set_exception(e)
                    break

        await self._queue.put(wrapper())
        return await future

    async def stop(self) -> None:
        """
        Waits for the execution of all queried tasks and returns, freeing allocated resources
        """
        await self._queue.join()
        self._producer_task.cancel()
        await self._rate_limited_queue.join()

        for c in self._consumers:
            c.cancel()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
