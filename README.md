# asgi-background

Background tasks for any ASGI framework.

## Example (Starlette)

```python
from asgi_background import BackgroundTaskMiddleware, BackgroundTasks
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


async def task(num: int) -> None:
    await anyio.sleep(1)
    print(num)


async def endpoint(request: Request) -> Response:
    tasks = BackgroundTasks(request.scope)
    await tasks.add_task(task, 1)
    return Response()


app = Starlette(
    routes=[Route("/", endpoint)],
    middleware=[Middleware(BackgroundTaskMiddleware)]
)
```
