import os
from types import TracebackType
from urllib.parse import urlparse

from pwn import context, remote

from ctf_solvers.types import ChallengeInstanceInfo


DEFAULT_HOST = 'challenge'
DEFAULT_PORT = 1337


class SolverError(Exception):
    """Custom exception for solver errors."""


class TicketedRemote:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port

    def __enter__(self) -> remote:
        with context.quiet:
            self.__r = remote(self.host, self.port)

        data = self.__r.recvuntil(b'?')
        data_str = data.decode()
        if 'ticket' not in data_str and 'token' not in data_str:
            self.__r.unrecv(data)
            return self.__r

        self.__r.sendline(os.getenv('TICKET', '').encode('utf8'))
        return self.__r

    def __exit__(
        self, type_: type[BaseException] | None, value: BaseException | None, traceback: TracebackType | None
    ) -> None:
        with context.quiet:
            self.__r.close()


def kill_instance(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    with TicketedRemote(host, port) as r:
        r.sendlineafter(b'?', b'3')
        with context.quiet:
            r.recvall()


def get_pwn_flag(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *dynamic_fields: str) -> str | None:
    with TicketedRemote(host, port) as r:
        r.sendlineafter(b'?', b'4')
        for field in dynamic_fields:
            r.sendlineafter(b'?', field.encode())
        with context.quiet:
            flag = r.recvline().decode().strip()

    return None if 'are you sure you solved it?' in flag else flag


def _compose_rpc_url(url: str) -> str:
    url_info = urlparse(url)
    return f'http://ctf-server-anvil-proxy:8545/{url_info.path.lstrip("/")}'


def _recv_instance(r: remote) -> ChallengeInstanceInfo:
    http_endpoint = r.recvline().decode().split('- ')[1].strip()
    ws_endpoint = r.recvline().decode().split('- ')[1].strip()
    r.recvuntil(b'private key: ')
    private_key = r.recvline().decode().strip()

    contracts: dict[str, str] = {}
    while True:
        try:
            line = r.recvline().decode()[2:]
        except (EOFError, TimeoutError):
            break
        contracts[line.split(' contract: ')[0]] = line.rsplit(':')[1].strip()

    return {
        'http_endpoint': http_endpoint,
        'http_endpoint_compose': _compose_rpc_url(http_endpoint),
        'ws_endpoint': ws_endpoint,
        'ws_endpoint_compose': _compose_rpc_url(ws_endpoint),
        'private_key': private_key,
        'contracts': contracts,
    }


def get_instance_info(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ChallengeInstanceInfo:
    with TicketedRemote(host, port) as r:
        r.sendlineafter(b'?', b'2')
        try:
            r.recvuntil(b'- rpc endpoints:\n')
        except EOFError as err:
            msg = 'Failed to get instance info, perhaps its not running.'
            raise SolverError(msg) from err
        return _recv_instance(r)


def launch_instance(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, get_if_running: bool = True
) -> ChallengeInstanceInfo:
    with TicketedRemote(host, port) as r:
        r.sendlineafter(b'?', b'1')
        try:
            r.recvuntil(b'- rpc endpoints:\n')
        except EOFError as err:
            # Probably already running
            if get_if_running:
                return get_instance_info(host, port)

            err_msg = 'Failed to get instance info, perhaps its already running.'
            raise SolverError(err_msg) from err
        return _recv_instance(r)
