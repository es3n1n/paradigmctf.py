import abc
import os
from os import environ

import requests


class TeamProviderError(Exception):
    """Custom exception for errors in team provider operations."""


CTFD_PUBLIC_URL: str = environ.get('CTFD_PUBLIC_URL', 'https://cr3c.tf/').rstrip('/')
CTFD_INTERNAL_URL: str = environ.get('CTFD_INTERNAL_URL', 'https://cr3c.tf/').rstrip('/')


class TeamProvider(abc.ABC):
    @abc.abstractmethod
    def get_team(self) -> str:
        pass


class CTFdTeamProvider(TeamProvider):
    def __init__(self) -> None:
        pass

    def get_team(self) -> str:
        try:
            token = input(f'token? you can get one at {CTFD_PUBLIC_URL}/settings ')
        except EOFError as err:
            msg = 'no token provided!'
            raise TeamProviderError(msg) from err

        team = self.get_team_by_ctfd_token(token)
        if not team:
            msg = 'failed to find team'
            raise TeamProviderError(msg)

        return str(team)

    @staticmethod
    def get_team_by_ctfd_token(ctfd_token: str) -> int | None:
        user_info = requests.get(
            f'{CTFD_INTERNAL_URL}/api/v1/users/me',
            headers={
                'User-Agent': 'paradigmctf.py',
                'Authorization': f'Token {ctfd_token}',
                'Content-Type': 'application/json',
            },
            timeout=60,
        ).json()
        if 'success' not in user_info or not user_info['success'] or 'data' not in user_info:
            return None
        if not isinstance(user_info['data'], dict) or 'team_id' not in user_info['data']:
            return None

        team_id: int = user_info['data']['team_id']
        if not isinstance(team_id, int):
            return None

        print(f'nice, authorized as team with id {team_id}')
        return team_id


class LocalTeamProvider(TeamProvider):
    def __init__(self, team_id: str) -> None:
        self._team_id = team_id

    def get_team(self) -> str:
        return self._team_id


def get_team_provider() -> TeamProvider:
    env = os.getenv('ENV', 'local')
    if env == 'local':
        return LocalTeamProvider(team_id='local')
    if env == 'ctfd':
        return CTFdTeamProvider()
    msg = f'unknown team provider: {env}'
    raise TeamProviderError(msg)
