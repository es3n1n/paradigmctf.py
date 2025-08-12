import os
import subprocess
from json import loads

from loguru import logger
from web3 import Web3

from ctf_launchers.types import ChallengeContract
from foundry.anvil import anvil_auto_impersonate_account


class DeployerError(Exception):
    """Custom exception for deployer errors."""


def _deserialize_deploy_response(response: str) -> list[ChallengeContract]:
    result: list[ChallengeContract] = []

    for line in response.splitlines():
        if len(line) == 0:
            continue

        item = loads(line)
        result.append({'name': item[0], 'address': item[1]})

    return result


def deploy(
    web3: Web3,
    project_location: str,
    mnemonic: str,
    deploy_script: str = 'script/Deploy.s.sol:Deploy',
    env: dict | None = None,
) -> list[ChallengeContract]:
    if env is None:
        env = {}
    anvil_auto_impersonate_account(web3, enabled=True)

    rfd, wfd = os.pipe2(os.O_NONBLOCK)  # type: ignore[attr-defined]

    env = {
        'PATH': '/opt/huff/bin:/opt/foundry/bin:/usr/bin:' + os.getenv('PATH', '/fake'),
        'MNEMONIC': mnemonic,
        'OUTPUT_FILE': f'/proc/self/fd/{wfd}',
    } | env
    args = [
        '/opt/foundry/bin/forge',
        'script',
        '--rpc-url',
        web3.provider.endpoint_uri,  # type: ignore[attr-defined]
        '--out',
        '/artifacts/out',
        '--cache-path',
        '/artifacts/cache',
        '--broadcast',
        '--unlocked',
        '--sender',
        '0x0000000000000000000000000000000000000000',
        deploy_script,
    ]

    logger.info(f'Deploying contracts with command: ({" ".join(args)}) and environment: {env}')
    proc = subprocess.Popen(
        args=args,
        env=env,
        pass_fds=[wfd],
        cwd=project_location,
        text=True,
        encoding='utf8',
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate()

    anvil_auto_impersonate_account(web3, enabled=False)
    if proc.returncode != 0:
        msg = f'forge failed to run: {stdout!r}, {stderr!r}'
        raise DeployerError(msg)

    result = os.read(rfd, 1024).decode('utf8')

    os.close(rfd)
    os.close(wfd)
    return _deserialize_deploy_response(result)
