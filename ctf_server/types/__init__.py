import os
from typing import NotRequired

from eth_account import Account
from eth_account.account import LocalAccount
from eth_account.hdaccount import key_from_seed, seed_from_mnemonic
from typing_extensions import TypedDict
from web3 import Web3


DEFAULT_IMAGE = 'ghcr.io/foundry-rs/foundry:latest'
DEFAULT_DERIVATION_PATH = "m/44'/60'/0'/0/"
DEFAULT_ACCOUNTS = 10
DEFAULT_BALANCE = 1000
DEFAULT_MNEMONIC = 'test test test test test test test test test test test junk'

PUBLIC_HOST = os.getenv('PUBLIC_HOST', 'http://127.0.0.1:8545').rstrip('/')


class LaunchAnvilInstanceArgs(TypedDict):
    image: NotRequired[str | None]
    accounts: NotRequired[int | None]
    balance: NotRequired[float | None]
    derivation_path: NotRequired[str | None]
    mnemonic: NotRequired[str | None]
    fork_url: NotRequired[str | None]
    fork_block_num: NotRequired[int | None]
    fork_chain_id: NotRequired[int | None]
    no_rate_limit: NotRequired[bool | None]
    chain_id: NotRequired[int | None]
    code_size_limit: NotRequired[int | None]
    block_time: NotRequired[int | None]
    extra_allowed_methods: NotRequired[list[str] | None]


def format_anvil_args(args: LaunchAnvilInstanceArgs, anvil_id: str, port: int = 8545) -> list[str]:
    cmd_args = []
    cmd_args += ['--host', '0.0.0.0']
    cmd_args += ['--port', str(port)]
    cmd_args += ['--accounts', '0']
    cmd_args += ['--state', f'/data/{anvil_id}-state.json']
    cmd_args += ['--state-interval', '5']

    if args.get('fork_url') is not None:
        cmd_args += ['--fork-url', str(args['fork_url'])]

    if args.get('fork_chain_id') is not None:
        cmd_args += ['--fork-chain-id', str(args['fork_chain_id'])]

    if args.get('fork_block_num') is not None:
        cmd_args += ['--fork-block-number', str(args['fork_block_num'])]

    if args.get('no_rate_limit'):
        cmd_args += ['--no-rate-limit']

    if args.get('chain_id') is not None:
        cmd_args += ['--chain-id', str(args['chain_id'])]

    if args.get('code_size_limit') is not None:
        cmd_args += ['--code-size-limit', str(args['code_size_limit'])]

    if args.get('block_time') is not None:
        cmd_args += ['--block-time', str(args['block_time'])]

    return cmd_args


class DaemonInstanceArgs(TypedDict):
    image: str


class CreateInstanceRequest(TypedDict):
    challenge_name: str
    instance_id: str
    timeout: int
    anvil_instances: NotRequired[dict[str, LaunchAnvilInstanceArgs]]
    daemon_instances: NotRequired[dict[str, DaemonInstanceArgs]]


class InstanceInfo(TypedDict):
    id: str
    ip: NotRequired[str]
    port: NotRequired[int]
    extra_allowed_methods: NotRequired[list[str] | None]


class UserData(TypedDict):
    instance_id: str
    external_id: str
    created_at: float
    expires_at: float
    anvil_instances: dict[str, InstanceInfo]
    daemon_instances: dict[str, InstanceInfo]
    metadata: dict


def get_account(mnemonic: str, offset: int) -> LocalAccount:
    seed = seed_from_mnemonic(mnemonic, '')
    private_key = key_from_seed(seed, f'{DEFAULT_DERIVATION_PATH}{offset}')

    return Account.from_key(private_key)


def get_player_account(mnemonic: str) -> LocalAccount:
    return get_account(mnemonic, 0)


def get_system_account(mnemonic: str) -> LocalAccount:
    return get_account(mnemonic, 1)


def get_additional_account(mnemonic: str, offset: int) -> LocalAccount:
    return get_account(mnemonic, offset + 2)


def get_privileged_web3(user_data: UserData, anvil_id: str) -> Web3:
    anvil_instance = user_data['anvil_instances'][anvil_id]
    return Web3(Web3.HTTPProvider(f'http://{anvil_instance["ip"]}:{anvil_instance["port"]}'))
