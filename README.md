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

## Execution model

The execution model is slightly different from Starlette's `BackgroundTasks` functionality.
The biggest difference is that Starlette executes tasks one at a time and doesn't start them until after the response is sent.
We execute them concurrently and start them as soon as they are scheduled.
Since Starlette executes tasks one by one, it also promises that if the first one fails (raises an exception) the second one won't be executed.
We make no such promise: we only promise that the tasks won't make the response wait for them, that's it.
You should not make any other assumptions about the execution model.

If background tasks fail, you'll get a stacktrace / stack dump, but no error information will be transmitted to the client.

## When to use this functionality

You should only use these background tasks for tasks that:

1. Only take a couple seconds to complete (~30 sec max). Any longer than that and they'll run into issues being cancelled if the server process is terminated and such.
2. Do not do blocking-IO or lock up the interpreter GIL. This _will_ prevent responses from being sent.
3. Do not need to transmit errors or any other information to the client.
