#!/usr/bin/env python3
from ctf_launchers import PwnChallengeLauncher, current_challenge
from ctf_server.types import LaunchAnvilInstanceArgs


class Launcher(PwnChallengeLauncher):
    def get_anvil_instances(self) -> dict[str, LaunchAnvilInstanceArgs]:
        return {
            'main': self.get_anvil_instance(
                image='ghcr.io/es3n1n/foundry:latest',
                extra_allowed_methods=['debug_getRawReceipts'],
                gas_limit=100_000_000,
            ),
        }


current_challenge.bind(Launcher(project_location='/challenge/project'))


if __name__ == '__main__':
    current_challenge.run()
