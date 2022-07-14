from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, List, Optional

import anyio
import anyio.abc
from asgi_lifespan_middleware import LifespanMiddleware

from asgi_background._types import ASGIApp, Receive, Scope, Send

Task = Callable[[], Awaitable[None]]


class BackgroundTaskMiddleware:
    _tg: Optional[anyio.abc.TaskGroup]

    def __init__(self, app: ASGIApp) -> None:
        self._tg = None

        @asynccontextmanager
        async def lifespan(*args: Any) -> AsyncIterator[None]:
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
            async def coro(tsk: Task = task):
                await tsk()

            self._tg.start_soon(coro)
