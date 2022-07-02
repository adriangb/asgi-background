import functools
import sys
from typing import Awaitable, Callable, Coroutine, List

if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec
else:
    from typing import ParamSpec

from asgi_background._types import Scope

P = ParamSpec("P")


class BackgroundTasks:
    __slots__ = ("_tasks",)

    def __init__(self, scope: Scope) -> None:
        if "asgi-background" not in scope:  # pragma: no cover
            raise RuntimeError("BackgroundTaskMiddleware is not installed")
        self._tasks: "List[Callable[[], Awaitable[None]]]" = scope["asgi-background"]

    def add_task(
        self,
        call: Callable[P, Coroutine[None, None, None]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        self._tasks.append(functools.partial(call, *args, **kwargs))
