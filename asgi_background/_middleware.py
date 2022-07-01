import anyio
import anyio.abc

from asgi_background._types import ASGIApp, Receive, Scope, Send


class BackgroundTaskMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            await self._app(scope, receive, send)

        async with anyio.create_task_group() as tg:
            scope["asgi-background"] = tg
            async with anyio.CancelScope(shield=True):
                await self._app(scope, receive, send)
