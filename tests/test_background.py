from time import time
from typing import Any, List, Optional, Tuple

import anyio
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from asgi_background import BackgroundTaskMiddleware, BackgroundTasks, WouldBlock


def test_background_tasks() -> None:
    async def tsk(num: int, resp_sent: anyio.Event, done: anyio.Event) -> None:
        assert num == 1
        # if this task held up the response, this would never yield back
        await resp_sent.wait()
        done.set()

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        await tasks.add_task(tsk, 1, request.scope["resp-sent"], request.scope["done"])
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


@pytest.mark.parametrize(
    "max_workers, expected_overlap",
    [
        (None, True),
        (1, False),
    ],
)
def test_background_add_task_backpressure(
    max_workers: Optional[int],
    expected_overlap: bool,
) -> None:
    times: List[Tuple[float, float]] = []

    async def tsk() -> None:
        start = time()
        await anyio.sleep(1)
        stop = time()
        times.append((start, stop))

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        await tasks.add_task(tsk)
        return Response()

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = BackgroundTaskMiddleware(app, max_workers=max_workers)

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        resp = client.get("/")
        assert resp.status_code == 200

    overlap = min(times[0][1], times[1][1]) - max(times[0][0], times[1][0]) > 0
    assert overlap is expected_overlap, times


def test_background_add_task_no_wait() -> None:

    times: List[Tuple[float, float]] = []

    async def tsk() -> None:
        start = time()
        await anyio.sleep(1)
        stop = time()
        times.append((start, stop))

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        tasks.add_task_no_wait(tsk)
        tasks.add_task_no_wait(tsk)
        return Response()

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = BackgroundTaskMiddleware(app, max_workers=None)

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        resp = client.get("/")
        assert resp.status_code == 200

    overlap = min(times[0][1], times[1][1]) - max(times[0][0], times[1][0]) > 0
    assert overlap is True, times


def test_background_add_task_no_wait_would_block() -> None:
    async def tsk() -> None:
        await anyio.sleep(1)

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        tasks.add_task_no_wait(tsk)
        with pytest.raises(WouldBlock):
            tasks.add_task_no_wait(tsk)
        return Response()

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = BackgroundTaskMiddleware(app, max_workers=1)

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200


def test_error_raised_in_background(caplog: Any) -> None:
    class MyError(Exception):
        pass

    async def tsk() -> None:
        raise MyError

    async def endpoint(request: Request) -> Response:
        tasks = BackgroundTasks(request.scope)
        await tasks.add_task(tsk)
        return Response()

    app: ASGIApp
    app = Starlette(routes=[Route("/", endpoint)])
    app = BackgroundTaskMiddleware(app)

    # there should be no error raised, just logged
    called = False
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200, resp.content
        called = True

    assert called
    assert "Exception in background task" in caplog.messages
