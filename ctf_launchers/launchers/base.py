import os
from time import time

import requests
from eth_abi import abi
from eth_account.hdaccount import generate_mnemonic
from pydantic import BaseModel
from web3 import Web3

from ctf_launchers.core.deployer import deploy
from ctf_launchers.types import ChallengeContract
from ctf_launchers.utils import http_url_to_ws
from ctf_server.types import (
    DEFAULT_MNEMONIC,
    CreateInstanceRequest,
    DaemonInstanceArgs,
    LaunchAnvilInstanceArgs,
    UserData,
    get_player_account,
    get_privileged_web3,
)


CHALLENGE = os.getenv('CHALLENGE', 'challenge')

ORCHESTRATOR_HOST = os.getenv('ORCHESTRATOR_HOST', 'http://orchestrator:7283').rstrip('/')
PUBLIC_HOST = os.getenv('PUBLIC_HOST', 'http://127.0.0.1:8545').rstrip('/')
PUBLIC_WEBSOCKET_HOST = http_url_to_ws(PUBLIC_HOST)

ETH_RPC_URL = os.getenv('ETH_RPC_URL')
INSTANCE_LIFE_TIME = int(os.getenv('INSTANCE_LIFE_TIME', '900'))  # 15 minutes by default

DEFAULT_PROJECT_LOCATION = 'challenge/project'


class NonSensitiveError(Exception):
    pass


class RPCInstance(BaseModel):
    http: str
    ws: str


class ContractInfo(BaseModel):
    address: str


class LaunchedInstance(BaseModel):
    expires_at: float
    expires_in_sec: float
    rpc_endpoints: dict[str, RPCInstance]
    player_private_key: str
    contracts: dict[str, ContractInfo]

    @classmethod
    def parse_instance(
        cls,
        user_data: UserData,
        mnemonic: str | None = None,
        challenge_contracts: list[ChallengeContract] | None = None,
    ) -> 'LaunchedInstance':
        if not mnemonic:
            mnemonic = user_data.get('metadata', {}).get('mnemonic', DEFAULT_MNEMONIC)
        if not challenge_contracts:
            challenge_contracts = user_data.get('metadata', {}).get('challenge_contracts', [])

        expires_at = user_data.get('expires_at', 0)
        return cls(
            expires_at=expires_at,
            expires_in_sec=expires_at - time(),
            rpc_endpoints={
                anvil_id: RPCInstance(
                    http=f'{PUBLIC_HOST}/{user_data["external_id"]}/{anvil_id}',
                    ws=f'{PUBLIC_WEBSOCKET_HOST}/{user_data["external_id"]}/{anvil_id}/ws',
                )
                for anvil_id in user_data.get('anvil_instances', [])
            },
            player_private_key=get_player_account(mnemonic).key.hex(),
            contracts={contract['name']: ContractInfo(address=contract['address']) for contract in challenge_contracts},
        )


class TeamInstanceLauncherBase:
    def __init__(
        self,
        project_location: str = DEFAULT_PROJECT_LOCATION,
        dynamic_fields: list[str] | None = None,
    ) -> None:
        self.dynamic_fields = dynamic_fields if dynamic_fields else []
        self.project_location = project_location
        self._mnemonic: str | None = None

    @property
    def mnemonic(self) -> str:
        if self._mnemonic:
            return self._mnemonic
        self._mnemonic = generate_mnemonic(12, lang='english')
        return self._mnemonic

    def get_anvil_instances(self) -> dict[str, LaunchAnvilInstanceArgs]:
        return {
            'main': self.get_anvil_instance(),
        }

    def get_daemon_instances(self) -> dict[str, DaemonInstanceArgs]:
        return {}

    def get_anvil_instance(self, **kwargs: int | str | list[str] | None) -> LaunchAnvilInstanceArgs:
        if 'balance' not in kwargs:
            kwargs['balance'] = 1000
        if 'accounts' not in kwargs:
            kwargs['accounts'] = 2
        if 'fork_url' not in kwargs:
            kwargs['fork_url'] = ETH_RPC_URL
        if 'mnemonic' not in kwargs:
            kwargs['mnemonic'] = self.mnemonic
        return LaunchAnvilInstanceArgs(**kwargs)  # type: ignore[typeddict-item]

    def _get_instance_id(self, team: str) -> str:
        return f'blockchain-{CHALLENGE}-{team}'.lower()

    # TODO(es3n1n, 28.03.24): create a type alias for metadata and replace it everywhere
    def update_metadata(self, new_metadata: dict[str, str | list[ChallengeContract]], team: str) -> bool:
        resp = requests.post(
            f'{ORCHESTRATOR_HOST}/instances/{self._get_instance_id(team)}/metadata',
            json=new_metadata,
            timeout=60,
        )
        body = resp.json()
        return bool(body.get('ok'))

    def launch_instance(self, team: str) -> LaunchedInstance:
        self._report_status('creating private blockchain...')
        body = requests.post(
            f'{ORCHESTRATOR_HOST}/instances',
            json=CreateInstanceRequest(
                challenge_name=CHALLENGE,
                instance_id=self._get_instance_id(team),
                timeout=INSTANCE_LIFE_TIME,
                anvil_instances=self.get_anvil_instances(),
                daemon_instances=self.get_daemon_instances(),
            ),
            timeout=60,
        ).json()
        if not body['ok']:
            raise NonSensitiveError(body['message'])

        user_data = body['data']

        self._report_status('deploying challenge...')
        challenge_contracts = self.deploy(user_data, self.mnemonic)

        if not self.update_metadata({'mnemonic': self.mnemonic, 'challenge_contracts': challenge_contracts}, team):
            msg = 'unable to update metadata'
            raise NonSensitiveError(msg)

        self._report_status('your private blockchain has been set up!')
        return LaunchedInstance.parse_instance(
            user_data=user_data,
            challenge_contracts=challenge_contracts,
            mnemonic=self.mnemonic,
        )

    def instance_info(self, team: str) -> LaunchedInstance:
        body = requests.get(f'{ORCHESTRATOR_HOST}/instances/{self._get_instance_id(team)}', timeout=5).json()
        if not body['ok']:
            raise NonSensitiveError(body['message'])

        return LaunchedInstance.parse_instance(
            user_data=body['data'],
            mnemonic=body['data'].get('metadata', {}).get('mnemonic', DEFAULT_MNEMONIC),
            challenge_contracts=body['data'].get('metadata', {}).get('challenge_contracts', []),
        )

    def kill_instance(self, team: str) -> bool:
        resp = requests.delete(f'{ORCHESTRATOR_HOST}/instances/{self._get_instance_id(team)}', timeout=5)
        body = resp.json()
        self._report_status(body.get('message', 'no message'))
        return True

    def deploy(self, user_data: UserData, mnemonic: str) -> list[ChallengeContract]:
        web3 = get_privileged_web3(user_data, 'main')
        return deploy(web3, self.project_location, mnemonic, env=self.get_deployment_args(user_data))

    def get_deployment_args(self, _: UserData) -> dict[str, str]:
        # This method can be overridden to provide additional deployment arguments
        return {}

    def _report_status(self, status: str) -> None:
        pass

    def run(self) -> None:
        pass


class PwnTeamInstanceLauncherBase(TeamInstanceLauncherBase):
    def load_flag_value(self, _: str) -> str:
        # _ is the team id
        return os.getenv('FLAG', 'cr3{no_flag}')

    def get_flag(self, dynamic_fields: dict[str, str], team: str) -> str:
        instance_body = requests.get(f'{ORCHESTRATOR_HOST}/instances/{self._get_instance_id(team)}', timeout=5).json()
        if not instance_body['ok']:
            msg = 'are you sure instance is running?'
            raise NonSensitiveError(msg)

        user_data = instance_body['data']
        web3 = get_privileged_web3(user_data, 'main')
        if not self.is_solved(web3, user_data['metadata']['challenge_contracts'], dynamic_fields, team):
            msg = 'are you sure you solved it?'
            raise NonSensitiveError(msg)

        return self.load_flag_value(team)

    def is_contract_solved(self, web3: Web3, contract: ChallengeContract, _: dict[str, str], __: str) -> bool:
        # _ is dynamic_fields, which are not used in this method
        # __ is team, which is not used in this method
        (result,) = abi.decode(
            ['bool'],
            web3.eth.call(
                {
                    'to': contract['address'],
                    'data': web3.keccak(text='isSolved()')[:4],
                }
            ),
        )
        return result

    def is_solved(
        self, web3: Web3, contracts: list[ChallengeContract], dynamic_fields: dict[str, str], team: str
    ) -> bool:
        return all(self.is_contract_solved(web3, contract, dynamic_fields, team) for contract in contracts)


class CurrentChallengeContainer:
    def __init__(self) -> None:
        self._challenge: TeamInstanceLauncherBase | None = None

    def bind(self, challenge: TeamInstanceLauncherBase) -> None:
        self._challenge = challenge

    def run(self) -> None:
        if self._challenge is None:
            msg = 'no challenge bound to the current container'
            raise NonSensitiveError(msg)
        self._challenge.run()


# Global variable to hold the current challenge instance
current_challenge = CurrentChallengeContainer()
