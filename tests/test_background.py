from typing import Tuple

import anyio
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from asgi_background import BackgroundTaskMiddleware, BackgroundTasks


def test_background_tasks() -> None:
    # test the default options, passing *args and **kwargs directly
    async def tsk(num: int, start: anyio.Event, done: anyio.Event) -> None:
        assert num == 1
        await start.wait()
        done.set()

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        events: Tuple[anyio.Event, anyio.Event] = request.scope["events"]
        tasks.start_task(tsk, 1, *events)
        return Response()

    def event_middleware(app: ASGIApp) -> ASGIApp:
        # make sure that background tasks don't run
        # until after we send the response
        # just so we can verify that they _can_
        # run after we send the response
        # the only guarantee we make is that they won't
        # hold up the response from being sent
        async def call(scope: Scope, receive: Receive, send: Send) -> None:
            start = anyio.Event()
            done = anyio.Event()
            scope["events"] = start, done
            await app(scope, receive, send)
            assert not start.is_set() and not done.is_set()
            start.set()
            await done.wait()

        return call

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = event_middleware(app)
    app = BackgroundTaskMiddleware(app)

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200


def test_error_raised_before_response_is_sent() -> None:
    class MyError(Exception):
        pass

    async def tsk(event: anyio.Event) -> None:
        event.set()
        raise MyError

    response_sent = False

    async def endpoint(request: Request) -> Response:
        nonlocal response_sent
        tasks = BackgroundTasks(request.scope)
        event = anyio.Event()
        tasks.start_task(tsk, event)
        await event.wait()
        response_sent = True
        return Response()

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = BackgroundTaskMiddleware(app)

    client = TestClient(app)
    with pytest.raises(MyError):
        client.get("/")

    assert response_sent


def test_error_raised_after_response_is_sent() -> None:
    class MyError(Exception):
        pass

    async def tsk(start: anyio.Event) -> None:
        await start.wait()
        raise MyError

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        start: anyio.Event = request.scope["event"]
        tasks.start_task(tsk, start)
        return Response()

    response_sent = False

    def event_middleware(app: ASGIApp) -> ASGIApp:
        async def call(scope: Scope, receive: Receive, send: Send) -> None:
            nonlocal response_sent
            start = anyio.Event()
            scope["event"] = start
            await app(scope, receive, send)
            response_sent = True
            start.set()

        return call

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = event_middleware(app)
    app = BackgroundTaskMiddleware(app)

    client = TestClient(app)
    with pytest.raises(MyError):
        client.get("/")

    assert response_sent
