#!/usr/bin/env python3

from web3 import Web3

from ctf_launchers import PwnChallengeLauncher, current_challenge
from ctf_launchers.types import ChallengeContract


class Launcher(PwnChallengeLauncher):
    def is_solved(
        self, web3: Web3, contracts: list[ChallengeContract], dynamic_fields: dict[str, str], team: str
    ) -> bool:
        if dynamic_fields.get('hello') != 'world':
            return False
        # Dynamic field check passed, now call isSolved on all contracts
        return super().is_solved(web3, contracts, dynamic_fields, team)


current_challenge.bind(Launcher(project_location='/challenge/project', dynamic_fields=['hello']))


if __name__ == '__main__':
    current_challenge.run()
