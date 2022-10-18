import functools
import sys
from typing import Awaitable, Callable, Coroutine, List, Optional

if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec
else:
    from typing import ParamSpec

import anyio

from asgi_background._types import Scope

P = ParamSpec("P")


class BackgroundTasks:
    __slots__ = ("_tasks", "_semaphore")

    def __init__(self, scope: Scope) -> None:
        if "asgi-background.tasks" not in scope:  # pragma: no cover
            raise RuntimeError("BackgroundTaskMiddleware is not installed")
        self._tasks: "List[Callable[[], Awaitable[None]]]" = scope[
            "asgi-background.tasks"
        ]
        self._semaphore: "Optional[anyio.Semaphore]" = scope[
            "asgi-background.semaphore"
        ]

    async def add_task(
        self,
        call: Callable[P, Coroutine[None, None, None]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        if self._semaphore is not None:
            await self._semaphore.acquire()
        self._tasks.append(functools.partial(call, *args, **kwargs))
