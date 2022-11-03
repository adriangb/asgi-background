from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from logging import getLogger
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

import anyio
import anyio.abc
from asgi_lifespan_middleware import LifespanMiddleware

from asgi_background._types import ASGIApp, Receive, Scope, Send

Task = Callable[[], Awaitable[None]]


logger = getLogger(__name__)


# start_soon requires a coroutine
# and we also want to log exceptions instead of crashing
async def coro_wrapper(tsk: Task) -> None:
    try:
        await tsk()
        return
    except Exception:
        # log and swallow the exception
        # this is the same behavior Quart uses (explicitly)
        # Starlette lets it bubble up and Uvicorn catches and logs it
        # but also swallows it
        logger.exception("Exception in background task")


class BackgroundTaskMiddleware:
    _schedule: Optional[Callable[[Task], Awaitable[None]]]
    _schedule_no_wait: Optional[Callable[[Task], None]]

    __slots__ = ("_app", "_schedule", "_schedule_no_wait", "_max_workers", "_started")

    def __init__(self, app: ASGIApp, max_workers: Optional[int] = 1024) -> None:
        if max_workers is not None and max_workers < 1:
            raise ValueError("max_workers must be larger than 1 or None")
        self._max_workers = max_workers
        self._started = False
        self._schedule = None
        self._schedule_no_wait = None

        @asynccontextmanager
        async def lifespan(*_1: Any) -> "AsyncIterator[None]":
            if self._started is True:
                raise RuntimeError(
                    "Lifespan called twice on"
                    f" the same {self.__class__.__name__} object"
                )
            try:
                async with AsyncExitStack() as stack:
                    tg = await stack.enter_async_context(anyio.create_task_group())
                    if self._max_workers is None:

                        async def schedule(task: Task) -> None:
                            tg.start_soon(coro_wrapper, task)

                        def schedule_no_wait(task: Task) -> None:
                            tg.start_soon(coro_wrapper, task)

                        self._schedule = schedule
                        self._schedule_no_wait = schedule_no_wait
                    else:
                        send, rcv = anyio.create_memory_object_stream(  # type: ignore
                            self._max_workers - 1, item_type=Task
                        )
                        send = await stack.enter_async_context(send)

                        async def worker() -> None:
                            async for task in rcv:
                                await coro_wrapper(task)

                        for _2 in range(self._max_workers):
                            tg.start_soon(worker)

                        def schedule_no_wait(task: Task) -> None:
                            send.send_nowait(task)

                        self._schedule = send.send
                        self._schedule_no_wait = schedule_no_wait
                    self._started = True
                    yield
            finally:
                self._started = False

        self._app = LifespanMiddleware(app, lifespan=lifespan)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            await self._app(scope, receive, send)
            return

        if self._started is False:  # pragma: no cover
            raise RuntimeError("Lifespan was not called")

        assert self._schedule is not None
        assert self._schedule_no_wait is not None
        scope["asgi-background._schedule"] = self._schedule
        scope["asgi-background._schedule_no_wait"] = self._schedule_no_wait

        await self._app(scope, receive, send)
