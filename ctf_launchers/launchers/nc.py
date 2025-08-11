import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from ctf_launchers.core.team_provider import TeamProvider, get_team_provider

from .base import (
    DEFAULT_PROJECT_LOCATION,
    LaunchedInstance,
    NonSensitiveError,
    PwnTeamInstanceLauncherBase,
    TeamInstanceLauncherBase,
)


@dataclass(frozen=True)
class Action:
    name: str
    handler: Callable[[], int]


class NCBaseLauncher(TeamInstanceLauncherBase):
    def __init__(
        self,
        project_location: str = DEFAULT_PROJECT_LOCATION,
        provider: TeamProvider = get_team_provider(),  # noqa: B008
    ) -> None:
        super().__init__(provider.get_team(), project_location)
        self._actions = [
            Action(name='launch new instance', handler=self.cli_launch_instance),
            Action(name='instance info', handler=self.cli_instance_info),
            Action(name='kill instance', handler=self.cli_kill_instance),
        ]

    def run(self) -> None:
        for i, action in enumerate(self._actions):
            print(f'{i + 1} - {action.name}')

        try:
            handler = self._actions[int(input('action? ')) - 1]
        except (KeyError, ValueError, IndexError, EOFError):
            sys.exit(1)

        try:
            sys.exit(handler.handler())
        except NonSensitiveError as e:
            print('error:', e)
            sys.exit(1)
        except Exception:
            print('an unexpected error occurred, please report it to the organizers (not the team)')
            traceback.print_exc()
            sys.exit(1)

    def cli_launch_instance(self) -> int:
        return self._show_instance(self.launch_instance())

    def cli_instance_info(self) -> int:
        return self._show_instance(self.instance_info())

    def cli_kill_instance(self) -> int:
        return int(not self.kill_instance())

    def _report_status(self, status: str) -> None:
        print(status, flush=True)

    def _show_instance(self, instance: LaunchedInstance) -> int:
        print('---- instance info ----')
        print(f'- will be terminated in: {instance.expires_in_sec / 60:.2f} minutes')
        print('- rpc endpoints:')
        for endpoint in instance.rpc_endpoints.values():
            print(f'    - {endpoint.http}')
            print(f'    - {endpoint.ws}')

        print(f'- your private key: {instance.player_private_key}')
        for name, contract in instance.contracts.items():
            print(f'- {name} contract: {contract.address}')
        return 0


class NCPwnLauncher(PwnTeamInstanceLauncherBase, NCBaseLauncher):
    def __init__(
        self,
        project_location: str = DEFAULT_PROJECT_LOCATION,
        provider: TeamProvider = get_team_provider(),  # noqa: B008
    ) -> None:
        super().__init__(project_location, provider)
        self._actions.append(Action(name='get flag', handler=self.cli_get_flag))

    def cli_get_flag(self) -> int:
        print(self.get_flag(), flush=True)
        return 0
