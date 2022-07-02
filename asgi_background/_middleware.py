from typing import Awaitable, Callable, List

from asgi_background._types import ASGIApp, Receive, Scope, Send


class BackgroundTaskMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            await self._app(scope, receive, send)

        tasks: "List[Callable[[], Awaitable[None]]]"
        tasks = scope["asgi-background"] = []
        await self._app(scope, receive, send)
        for task in tasks:
            await task()
