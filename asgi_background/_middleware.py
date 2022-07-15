from contextlib import asynccontextmanager
from logging import getLogger
from typing import Any, AsyncIterator, Awaitable, Callable, List, Optional

import anyio
import anyio.abc
from asgi_lifespan_middleware import LifespanMiddleware

from asgi_background._types import ASGIApp, Receive, Scope, Send

Task = Callable[[], Awaitable[None]]


logger = getLogger(__name__)


class BackgroundTaskMiddleware:
    _tg: Optional[anyio.abc.TaskGroup]

    def __init__(self, app: ASGIApp) -> None:
        self._tg = None

        @asynccontextmanager
        async def lifespan(*args: Any) -> AsyncIterator[None]:
            if self._tg is not None:  # pragma: no cover
                raise RuntimeError(
                    "Lifespan called twice on"
                    " the same BackgroundTaskMiddleware object"
                )
            try:
                async with anyio.create_task_group() as tg:
                    self._tg = tg
                    yield
            finally:
                self._tg = None

        self._app = LifespanMiddleware(app, lifespan=lifespan)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            await self._app(scope, receive, send)
            return

        if self._tg is None:  # pragma: no cover
            raise RuntimeError("Lifespan was not called")

        tasks: "List[Task]"
        tasks = scope["asgi-background"] = []
        await self._app(scope, receive, send)
        for task in tasks:
            # start_soon requires a coroutine
            # and we also want to log exceptions instead of crashing
            async def coro(tsk: Task = task):
                try:
                    await tsk()
                except Exception:
                    # log and swallow the exception
                    # this is the same behavior Quart uses (explicitly)
                    # Starlette lets it bubble up and Uvicorn catches and logs it
                    # but also swallows it
                    logger.exception("Exception in background task")

            self._tg.start_soon(coro)
