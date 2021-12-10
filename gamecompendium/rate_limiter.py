import asyncio
from typing import TypeVar, Awaitable, Callable

T = TypeVar('T')


class RateLimitExceedException(Exception):
    pass


class RateLimiter:
    def __init__(self, tasks_per_seconds, max_tasks_at_once):
        self._tasks_per_second = tasks_per_seconds
        self._queue = asyncio.Queue()
        self._rate_limited_queue = asyncio.Queue()
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

    async def stop(self):
        await self._queue.join()
        self._producer_task.cancel()
        await self._rate_limited_queue.join()

        for c in self._consumers:
            c.cancel()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
