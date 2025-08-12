import inspect
import os
from pathlib import Path

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from .base import (
    CHALLENGE,
    DEFAULT_PROJECT_LOCATION,
    LaunchedInstance,
    NonSensitiveError,
    PwnTeamInstanceLauncherBase,
    TeamInstanceLauncherBase,
)


BIND_HOST = os.getenv('BIND_HOST', '0.0.0.0')
BIND_PORT = int(os.getenv('BIND_PORT', '1337'))
WORKERS_AMOUNT = int(os.getenv('WORKERS_AMOUNT', '2'))


class LaunchFormForm(BaseModel):
    team_id: str


class FlagResponse(BaseModel):
    flag: str


class APIBaseLauncher(TeamInstanceLauncherBase):
    def __init__(
        self,
        project_location: str = DEFAULT_PROJECT_LOCATION,
        dynamic_fields: list[str] | None = None,
    ) -> None:
        super().__init__(project_location=project_location, dynamic_fields=dynamic_fields)
        self._api: FastAPI = FastAPI(title=f'{CHALLENGE} private API')
        self._bind: bool = False
        frame = inspect.currentframe()
        # FIXME(es3n1n): this is sketchy, but we need to get the challenge module name
        self._challenge_module_name = Path(frame.f_back.f_back.f_globals['__file__']).stem  # type: ignore[union-attr]

    def run(self) -> None:
        uvicorn.run(
            f'{self._challenge_module_name}:current_challenge._challenge.api',
            host=BIND_HOST,
            port=BIND_PORT,
            server_header=False,
            workers=WORKERS_AMOUNT,
        )

    def _bind_v1(self, router: APIRouter) -> None:
        @router.put('/instance')
        def launch_instance(form: LaunchFormForm) -> LaunchedInstance:
            return self.launch_instance(form.team_id)

        @router.get('/instance')
        def get_instance_info(team_id: str) -> LaunchedInstance:
            return self.instance_info(team_id)

        @router.delete('/instance')
        def kill_instance(team_id: str) -> bool:
            return self.kill_instance(team_id)

    def _bind_routes(self) -> None:
        @self._api.exception_handler(NonSensitiveError)
        def non_sensitive_error_handler(_: Request, exc: NonSensitiveError) -> JSONResponse:
            return JSONResponse(
                status_code=400,
                content={'detail': str(exc)},
            )

        v1 = APIRouter(prefix='/v1')
        self._bind_v1(v1)
        self._api.include_router(v1)

    @property
    def api(self) -> FastAPI:
        if not self._bind:
            self._bind_routes()
            self._bind = True
        return self._api


class APIPwnLauncher(APIBaseLauncher, PwnTeamInstanceLauncherBase):
    def __init__(
        self,
        project_location: str = DEFAULT_PROJECT_LOCATION,
        dynamic_fields: list[str] | None = None,
    ) -> None:
        super().__init__(project_location=project_location, dynamic_fields=dynamic_fields)

    def _bind_v1(self, router: APIRouter) -> None:
        super()._bind_v1(router)
        pwn_router = APIRouter(prefix='/pwn')

        @pwn_router.get('/flag')
        def get_flag(request: Request, team_id: str) -> FlagResponse:
            get_params = request.query_params
            for dyn_field in self.dynamic_fields:
                if dyn_field not in get_params:
                    msg = f'missing dynamic field {dyn_field}'
                    raise NonSensitiveError(msg)

            return FlagResponse(flag=self.get_flag(dict(get_params), team_id))

        router.include_router(pwn_router)
