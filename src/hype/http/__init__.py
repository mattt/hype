import asyncio
import warnings
from contextlib import asynccontextmanager
from typing import Annotated

from docstring_parser import parse as parse_docstring
from fastapi import APIRouter, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, create_model

from hype.function import Function
from hype.http.prefer import parse_prefer_headers
from hype.http.problem import Problem, problem_exception_handler
from hype.task import Tasks


class FileUploadRequest(BaseModel):
    file: UploadFile


def create_file_upload_callback_router(source_operation_id: str) -> APIRouter:
    router = APIRouter()

    @router.put(
        "{$callback_url}/files/{$request.body.id}",
        operation_id=f"{source_operation_id}_file_upload_callback",
        summary="File upload callback endpoint",
    )
    def upload_file(
        request: FileUploadRequest = File(...),  # pylint: disable=unused-argument
    ) -> Response:
        return Response(status_code=204)

    return router


def add_fastapi_endpoint(
    app: FastAPI,
    func: Function,
) -> None:
    path = f"/{func.name}"

    # Create a new input model with a unique name

    name = func.name
    docstring = parse_docstring(func._wrapped.__doc__ or "")  # pylint: disable=protected-access
    summary = docstring.short_description
    description = docstring.long_description
    operation_id = func.name

    input = create_model(
        f"{operation_id}_Input",
        __base__=func.input,
    )

    output = create_model(
        f"{operation_id}_Output",
        __base__=func.output,
    )

    callbacks = None
    if False:  # TODO: Add file upload callback # pylint: disable=using-constant-test
        callbacks = create_file_upload_callback_router(operation_id).routes

    @app.post(
        path,
        name=name,
        summary=summary,
        description=description,
        operation_id=operation_id,
        callbacks=callbacks,
        responses={
            "default": {"model": Problem, "description": "Default error response"}
        },
    )
    async def endpoint(
        input: input,  # type: ignore
        prefer: Annotated[list[str] | None, Header()] = None,
    ) -> output:  # type: ignore
        preferences = parse_prefer_headers(prefer)

        input_dict = input.model_dump(mode="python")
        if asyncio.iscoroutinefunction(func):
            task = asyncio.create_task(func(**input_dict))
        else:
            coroutine = asyncio.to_thread(func, **input_dict)
            task = asyncio.create_task(coroutine)

        id = app.state.tasks.defer(task)
        done, _ = await asyncio.wait(
            [task],
            timeout=preferences.wait,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if done:
            return done.pop().result()
        else:
            # If task was not completed within `wait` seconds, return the 202 response.
            return JSONResponse(
                status_code=202, content=None, headers={"Location": f"/tasks/{id}"}
            )


def create_fastapi_app(
    functions: list[Function],
    title: str = "Hype API",
    summary: str | None = None,
    description: str = "",
    version: str = "0.1.0",
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN202
        app.state.tasks = Tasks()

        for function in functions:
            add_fastapi_endpoint(app, function)

        yield

        await app.state.tasks.wait_until_empty()

    app = FastAPI(
        title=title,
        summary=summary,
        description=description,
        version=version,
        lifespan=lifespan,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            from opentelemetry.instrumentation.fastapi import (  # pylint: disable=import-outside-toplevel
                FastAPIInstrumentor,
            )

            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass

    app.add_exception_handler(ValueError, problem_exception_handler)
    app.add_exception_handler(HTTPException, problem_exception_handler)
    app.add_exception_handler(RequestValidationError, problem_exception_handler)

    @app.get("/tasks/{id}", include_in_schema=False)
    def get_task(id: str) -> JSONResponse:
        task = app.state.tasks.get(id)

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found") from None

        return JSONResponse(status_code=200, content=task.to_dict())

    @app.post("/tasks/{id}/cancel", include_in_schema=False)
    def cancel_task(id: str) -> JSONResponse:
        task = app.state.tasks.get(id)

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found") from None

        task.cancel()
        return JSONResponse(status_code=200, content=task.to_dict())

    @app.get("/openapi.json", include_in_schema=False)
    def get_openapi_schema() -> dict:
        return app.openapi()

    return app
