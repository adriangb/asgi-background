import functools
from typing import Callable, Coroutine, ParamSpec

import anyio.abc

from asgi_background._types import Scope

P = ParamSpec("P")


class BackgroundTasks:
    __slots__ = ("_tg",)
    _tg: anyio.abc.TaskGroup

    def __init__(self, scope: Scope) -> None:
        if "asgi-background" not in scope:  # pragma: no cover
            raise RuntimeError("BackgroundTaskMiddleware is not installed")
        self._tg = scope["asgi-background"]

    def start_task(
        self,
        call: Callable[P, Coroutine[None, None, None]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        self._tg.start_soon(functools.partial(call, *args, **kwargs))
