import typing
import sys
if sys.version_info < (3, 8):
    from typing_extensions import Protocol
else:
    from typing import Protocol

Scope = typing.MutableMapping[str, typing.Any]
Message = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[Message]]
Send = typing.Callable[[Message], typing.Awaitable[None]]


class ASGIApp(Protocol):
    def __call__(self, __scope: Scope, __receive: Receive, __send: Send) -> typing.Awaitable[None]:
        ...
