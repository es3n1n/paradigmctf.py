import inspect
import os
from pathlib import Path
from typing import cast

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


class APIBaseLauncher:
    def __init__(
        self,
        base: type[TeamInstanceLauncherBase] = TeamInstanceLauncherBase,
        project_location: str = DEFAULT_PROJECT_LOCATION,
    ) -> None:
        self._base = base
        self._project_location = project_location
        self._api = FastAPI(title=f'{CHALLENGE} private api')

        frame = inspect.currentframe()
        # FIXME(es3n1n): this is sketchy, but we need to get the challenge module name
        self._challenge_module_name = Path(frame.f_back.f_back.f_globals['__file__']).stem  # type: ignore[union-attr]
        self._bind: bool = False

    def run(self) -> None:
        uvicorn.run(
            f'{self._challenge_module_name}:current_challenge._challenge.api',
            host=BIND_HOST,
            port=BIND_PORT,
            server_header=False,
            workers=WORKERS_AMOUNT,
        )

    def _construct_base(self, team_id: str) -> TeamInstanceLauncherBase:
        return self._base(team_id, self._project_location)

    def _bind_v1(self, router: APIRouter) -> None:
        @router.put('/instance')
        def launch_instance(form: LaunchFormForm) -> LaunchedInstance:
            launcher = self._construct_base(form.team_id)
            return launcher.launch_instance()

        @router.get('/instance')
        def get_instance_info(team_id: str) -> LaunchedInstance:
            launcher = self._construct_base(team_id)
            return launcher.instance_info()

        @router.delete('/instance')
        def kill_instance(team_id: str) -> bool:
            launcher = self._construct_base(team_id)
            return launcher.kill_instance()

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
    ) -> None:
        super().__init__(PwnTeamInstanceLauncherBase, project_location)

    def _bind_v1(self, router: APIRouter) -> None:
        super()._bind_v1(router)

        pwn_router = APIRouter(prefix='/pwn')

        @pwn_router.get('/flag')
        def get_flag(team_id: str) -> FlagResponse:
            launcher = cast('PwnTeamInstanceLauncherBase', self._construct_base(team_id))
            return FlagResponse(flag=launcher.get_flag())

        router.include_router(pwn_router)
