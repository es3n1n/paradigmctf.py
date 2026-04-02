import time
from json import dumps, loads
from typing import Any, Never, cast

import redis

from ctf_server.types import UserData

from .database import Database


class RedisDatabaseError(Exception):
    """Custom exception for Redis database errors."""


class RedisDatabase(Database):
    def __init__(self, url: str, redis_kwargs: dict[str, Any] | None = None) -> None:
        if redis_kwargs is None:
            redis_kwargs = {}
        super().__init__()

        self.__client: redis.Redis = redis.Redis.from_url(
            url,
            decode_responses=True,
            **redis_kwargs,
        )

    def register_instance(self, _: str, instance: UserData) -> None:
        pipeline = self.__client.pipeline()

        try:
            pipeline.json().set(f'instance/{instance["instance_id"]}', '$', instance)  # type: ignore[call-arg,arg-type]
            pipeline.hset('external_ids', instance['external_id'], instance['instance_id'])
            pipeline.zadd(
                'expiries',
                {
                    instance['instance_id']: int(instance['expires_at']),
                },
            )
        finally:
            pipeline.execute()

    def update_instance(self, _: str, __: UserData) -> Never:
        msg = 'not supported'
        raise RedisDatabaseError(msg)

    def unregister_instance(self, instance_id: str) -> UserData | None:
        instance = cast('UserData | None', self.__client.json().get(f'instance/{instance_id}'))
        if instance is None:
            return None

        pipeline = self.__client.pipeline()
        try:
            pipeline.json().delete(f'instance/{instance_id}')
            pipeline.hdel('external_ids', instance['external_id'])
            pipeline.zrem('expiries', instance_id)
            pipeline.delete(f'metadata/{instance_id}')
            return cast('UserData', instance)
        finally:
            pipeline.execute()

    def get_instance(self, instance_id: str) -> UserData | None:
        instance = cast('UserData | None', self.__client.json().get(f'instance/{instance_id}'))
        if instance is None:
            return None

        instance['metadata'] = {}
        metadata = self.__client.hgetall(f'metadata/{instance_id}')
        if metadata is not None:
            metadata = {k: loads(v) for k, v in metadata.items()}  # type: ignore[union-attr]
            instance['metadata'] = metadata

        return instance

    def get_instance_by_external_id(self, rpc_id: str) -> UserData | None:
        instance_id = self.__client.hget('external_ids', rpc_id)
        if instance_id is None:
            return None

        return self.get_instance(instance_id)  # type: ignore[arg-type]

    def get_all_instances(self) -> list[UserData]:
        return [
            instance
            for key in self.__client.scan_iter(match='instance/*')
            if (instance := self.get_instance(key.split('/')[1]))  # type: ignore[union-attr]
        ]

    def get_expired_instances(self) -> list[UserData]:
        instance_ids = self.__client.zrange('expiries', 0, int(time.time()), byscore=True)
        return [instance for instance_id in instance_ids if (instance := self.get_instance(instance_id))]  # type: ignore[union-attr]

    def update_metadata(self, instance_id: str, metadata: dict[str, str | list[dict[str, str]]]) -> None:
        pipeline = self.__client.pipeline()
        try:
            for k, v in metadata.items():
                pipeline.hset(f'metadata/{instance_id}', k, dumps(v))
        finally:
            pipeline.execute()
