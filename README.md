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
    tasks.add_task(task, 1)
    return Response()


app = Starlette(
    routes=[Route("/", endpoint)],
    middleware=[Middleware(BackgroundTaskMiddleware)]
)
```

## Execution

Unlike Starlette, we do not execute background tasks within the ASGI request/response cycle.
Instead we schedule them in a `TaskGroup` that is bound to the application's lifespan.
The only guarantee we make is that background tasks will not block (in the async sense, not the GIL sense) sending the response and that we will (try) to wait for them to finish when the application shuts down.
Just like with Starlette's background tasks, you should only use these for short lived tasks, they are not a durable queuing mechanisms like Redis, Celery, etc.
For context, the default application shutdown grace period in Kubernetes is 30 seconds, so 30 seconds is probably about as long as you should allow your tasks to run.
