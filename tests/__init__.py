from pathlib import Path

from cheb3.utils import compile_file

from ctf_solvers.solver import SolverError, get_instance_info, get_pwn_flag, kill_instance, launch_instance
from ctf_solvers.types import ChallengeInstanceInfo


HOST = '127.0.0.1'


def compile_src_for(challenge: str, file: str, solc_version: str = 'latest') -> dict[str, tuple[dict, str]]:
    path = str(Path(__file__).parent.parent / 'examples' / challenge / 'project' / 'src' / file)
    return compile_file(path, solc_version=solc_version)


class Instance:
    def __init__(self, host: str = HOST, port: int = 1337) -> None:
        self.host = host
        self.port = port

    def get(self) -> ChallengeInstanceInfo | None:
        try:
            return get_instance_info(self.host, self.port)
        except SolverError:
            return None

    def kill(self) -> None:
        kill_instance(self.host, self.port)

    def launch(self, *, kill_if_exists: bool) -> ChallengeInstanceInfo:
        try:
            return launch_instance(self.host, self.port, get_if_running=not kill_if_exists)
        except SolverError:
            if not kill_if_exists:
                raise
        # If the instance is already running, kill it and relaunch
        self.kill()
        return launch_instance(self.host, self.port)

    def get_pwn_flag(self, *dynamic_fields: str) -> str | None:
        return get_pwn_flag(self.host, self.port, *dynamic_fields)


HELLO_PWN = Instance(port=31337)
EXTRA_METHODS_PWN = Instance(port=31338)
