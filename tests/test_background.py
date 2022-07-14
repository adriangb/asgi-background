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
    async def tsk(num: int, resp_sent: anyio.Event, done: anyio.Event) -> None:
        assert num == 1
        # if this task held up the response, this would never yield back
        await resp_sent.wait()
        done.set()

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        tasks.add_task(tsk, 1, request.scope["resp-sent"], request.scope["done"])
        return Response()

    def set_response_sent_middleware(app: ASGIApp) -> ASGIApp:
        async def call(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                return await app(scope, receive, send)
            resp_sent = anyio.Event()
            scope["resp-sent"] = resp_sent
            await app(scope, receive, send)
            assert not resp_sent.is_set()
            resp_sent.set()

        return call

    def check_done_middleware(app: ASGIApp) -> ASGIApp:
        # make sure that background tasks don't run
        # until after we send the response
        # just so we can verify that they _can_
        # run after we send the response
        # the only guarantee we make is that they won't
        # hold up the response from being sent
        async def call(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                return await app(scope, receive, send)
            done = anyio.Event()
            scope["done"] = done
            await app(scope, receive, send)
            await done.wait()

        return call

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = set_response_sent_middleware(app)
    app = BackgroundTaskMiddleware(app)
    app = check_done_middleware(app)

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        print("done")


def test_error_raised_in_background() -> None:
    class MyError(Exception):
        pass

    async def tsk(start: anyio.Event) -> None:
        await start.wait()
        raise MyError

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        start: anyio.Event = request.scope["event"]
        tasks.add_task(tsk, start)
        return Response()

    def event_middleware(app: ASGIApp) -> ASGIApp:
        async def call(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                return await app(scope, receive, send)
            start = anyio.Event()
            scope["event"] = start
            await app(scope, receive, send)
            start.set()

        return call

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = event_middleware(app)
    app = BackgroundTaskMiddleware(app)

    # the error should eb raised after the response is returned
    called = False
    with pytest.raises(MyError):
        with TestClient(app) as client:
            resp = client.get("/")
            assert resp.status_code == 200, resp.content
            called = True

    assert called
