import requests
from eth_abi import abi

from ctf_launchers.launcher import ORCHESTRATOR_HOST, Action, Launcher
from ctf_launchers.score_submitter import ScoreSubmitter, get_score_submitter
from ctf_launchers.team_provider import TeamProvider, get_team_provider
from ctf_server.types import UserData, get_privileged_web3


class KothChallengeLauncherError(Exception):
    """Custom exception for Koth challenge errors."""


class KothChallengeLauncher(Launcher):
    def __init__(
        self,
        project_location: str = 'challenge/project',
        provider: TeamProvider = get_team_provider(),  # noqa: B008
        submitter: ScoreSubmitter = get_score_submitter(),  # noqa: B008
        want_metadata: list[str] | None = None,
    ) -> None:
        if want_metadata is None:
            want_metadata = []
        super().__init__(
            project_location,
            provider,
            actions=[Action(name='submit score', handler=self.submit_score)],
        )

        self.__score_submitter = submitter
        self.__want_metadata = want_metadata

    def submit_score(self) -> int:
        instance_body = requests.get(f'{ORCHESTRATOR_HOST}/instances/{self.get_instance_id()}', timeout=5).json()
        if not instance_body['ok']:
            return 1

        user_data = instance_body['data']

        score = self.get_score(user_data, user_data['metadata']['challenge_address'])

        data = {}
        for metadata in self.__want_metadata:
            data[metadata] = user_data['metadata'][metadata]

        if self.team is None:
            msg = 'team is not set'
            raise KothChallengeLauncherError(msg)

        self.__score_submitter.submit_score(self.team, data, score)
        return 0

    def get_score(self, user_data: UserData, addr: str) -> bool:
        web3 = get_privileged_web3(user_data, 'main')

        (result,) = abi.decode(
            ['uint256'],
            web3.eth.call(
                {
                    'to': addr,
                    'data': web3.keccak(text='getScore()')[:4],
                }
            ),
        )

        return result
