from __future__ import annotations

import functools
import sys
from typing import Any, Awaitable, Callable, Coroutine

if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec
else:
    from typing import ParamSpec

import anyio

from asgi_background._types import Scope

P = ParamSpec("P")

Task = Callable[[], Awaitable[Any]]


class WouldBlock(Exception):
    """Raised when BackgroundTasks.add_task_no_wait is called
    without available workers to pick up the task.
    """


class BackgroundTasks:
    __slots__ = ("_schedule_no_wait", "_schedule")
    _schedule: Callable[[Task], Awaitable[None]]
    _schedule_no_wait: Callable[[Task], None]

    def __init__(self, scope: Scope) -> None:
        if "asgi-background._schedule" not in scope:  # pragma: no cover
            raise RuntimeError("BackgroundTaskMiddleware is not installed")
        self._schedule = scope["asgi-background._schedule"]
        self._schedule_no_wait = scope["asgi-background._schedule_no_wait"]

    async def add_task(
        self,
        call: Callable[P, Coroutine[None, None, None]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        """
        Schedule a background task to run in the background,
        waiting for an available worker if `max_workers` was
        passed to BackgroundTasksMiddleware.
        """
        await self._schedule(functools.partial(call, *args, **kwargs))

    def add_task_no_wait(
        self,
        call: Callable[P, Coroutine[None, None, None]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        """
        Schedule a background task to start immediately if there is a worker available.
        :raises ~asgi_background.WouldBlock: if there are no workers available
        """
        try:
            self._schedule_no_wait(functools.partial(call, *args, **kwargs))
        except anyio.WouldBlock as e:
            raise WouldBlock() from e
