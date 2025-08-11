import abc
import os
from typing import Any

import requests


class ScoreSubmitterError(Exception):
    """Custom exception for errors in score submission operations."""


type ScoreData = dict[str, Any] | str | int | float | list[Any] | None


class ScoreSubmitter(abc.ABC):
    @abc.abstractmethod
    def submit_score(self, team_id: str, data: ScoreData, score: int) -> None:
        pass


class RemoteScoreSubmitter(ScoreSubmitter):
    def __init__(self, host: str) -> None:
        self.__host = host

    def submit_score(self, team_id: str, data: ScoreData, score: int) -> None:
        secret = os.getenv('SECRET')
        challenge_id = os.getenv('CHALLENGE_ID')

        resp = requests.post(
            f'{self.__host}/api/internal/submit',
            headers={
                'Authorization': f'Bearer {secret}',
                'Content-Type': 'application/json',
            },
            json={
                'teamId': team_id,
                'challengeId': challenge_id,
                'data': data,
                'score': score,
            },
            timeout=60,
        ).json()

        if not resp['ok']:
            msg = f'failed to submit score: {resp["message"]}'
            raise ScoreSubmitterError(msg)

        print(f'score successfully submitted (id={resp["id"]})')


class LocalScoreSubmitter(ScoreSubmitter):
    def submit_score(self, team_id: str, data: ScoreData, score: int) -> None:
        print(f'submitted score for team {team_id}: {score} {data}')


def get_score_submitter() -> ScoreSubmitter:
    env = os.getenv('ENV', 'local')

    if env == 'local':
        return LocalScoreSubmitter()
    if env == 'dev':
        return RemoteScoreSubmitter(host='https://dev.ctf.paradigm.xyz')
    if env == 'prod':
        return RemoteScoreSubmitter(host='https://ctf.paradigm.xyz')

    msg = 'unsupported env'
    raise ScoreSubmitterError(msg)
