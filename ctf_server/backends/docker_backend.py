import http.client
import shlex
import time
from typing import TYPE_CHECKING

import docker
from docker.errors import APIError, NotFound
from docker.types import Mount
from loguru import logger
from web3 import Web3

from ctf_server.databases.database import Database
from ctf_server.types import (
    DEFAULT_IMAGE,
    CreateInstanceRequest,
    InstanceInfo,
    UserData,
    format_anvil_args,
    format_anvil_env,
)

from .backend import Backend


if TYPE_CHECKING:
    from docker.models.containers import Container
    from docker.models.volumes import Volume


# FIXME(es3n1n): Currently it is not possible in docker compose networking to allow us to make orchestrator talk to the
#  instances but not the other way around
INSTANCES_NETWORK_NAME = 'paradigmctf-instances'


class DockerBackend(Backend):
    def __init__(self, database: Database) -> None:
        self.__client = docker.from_env()

        # note(es3n1n, 28.03.24): We are initializing base backend after the client because it would start a container
        # prunner thread, and there could be an issue where there would be some expired instances that it will start
        # pruning them before we even init the client, which will result in undefined __client exceptions
        super().__init__(database)

    def _launch_instance_impl(self, request: CreateInstanceRequest) -> UserData:
        instance_id = request['instance_id']
        requested_anvil_instances = request['anvil_instances']

        volume: Volume = self.__client.volumes.create(name=instance_id)

        anvil_containers: dict[str, Container] = {}
        for anvil_id, anvil_args in requested_anvil_instances.items():
            anvil_containers[anvil_id] = self.__client.containers.run(  # type: ignore[call-overload]
                name=f'{instance_id}-{anvil_id}',
                image=anvil_args.get('image', DEFAULT_IMAGE),
                network=INSTANCES_NETWORK_NAME,
                entrypoint=['sh', '-c'],
                command=[
                    'while true; do anvil '
                    + ' '.join([shlex.quote(str(v)) for v in format_anvil_args(anvil_args, anvil_id)])
                    + '; sleep 1; done;'
                ],
                restart_policy={'Name': 'always'},
                detach=True,
                mounts=[
                    Mount(target='/data', source=volume.id),
                ],
                environment=format_anvil_env(anvil_args),
            )

        daemon_containers: dict[str, Container] = {}
        for daemon_id, daemon_args in request.get('daemon_instances', {}).items():
            daemon_containers[daemon_id] = self.__client.containers.run(
                name=f'{instance_id}-{daemon_id}',
                image=daemon_args['image'],
                network=INSTANCES_NETWORK_NAME,  # TODO(es3n1n): perhaps separate network?
                restart_policy={'Name': 'always'},
                detach=True,
                environment={
                    'INSTANCE_ID': instance_id,
                },
            )

        anvil_instances: dict[str, InstanceInfo] = {}
        for anvil_id, anvil_container in anvil_containers.items():
            container: Container = self.__client.containers.get(anvil_container.id)

            anvil_instances[anvil_id] = {
                'id': anvil_id,
                'ip': container.attrs['NetworkSettings']['Networks'][INSTANCES_NETWORK_NAME]['IPAddress'],
                'port': 8545,
            }
            self._remap_extra_anvil_keys(anvil_instances[anvil_id], requested_anvil_instances[anvil_id])

            self._prepare_node(
                request['anvil_instances'][anvil_id],
                Web3(
                    Web3.HTTPProvider(f'http://{anvil_instances[anvil_id]["ip"]}:{anvil_instances[anvil_id]["port"]}')
                ),
            )

        daemon_instances: dict[str, InstanceInfo] = {}
        for daemon_id in daemon_containers:
            daemon_instances[daemon_id] = {
                'id': daemon_id,
            }

        now = time.time()
        return UserData(
            instance_id=instance_id,
            external_id=self._generate_rpc_id(),
            created_at=now,
            expires_at=now + request['timeout'],
            anvil_instances=anvil_instances,
            daemon_instances=daemon_instances,
            metadata={},
        )

    def _cleanup_instance(self, args: CreateInstanceRequest) -> None:
        instance_id = args['instance_id']

        self.__try_delete(
            instance_id,
            list(args.get('anvil_instances', {}).keys()),
            list(args.get('daemon_instances', {}).keys()),
        )

    def kill_instance(self, instance_id: str) -> UserData | None:
        instance = self._database.unregister_instance(instance_id)
        if instance is None:
            return None

        self.__try_delete(
            instance_id,
            list(instance.get('anvil_instances', {}).keys()),
            list(instance.get('daemon_instances', {}).keys()),
        )

        return instance

    def __try_delete(self, instance_id: str, anvil_ids: list[str], daemon_ids: list[str]) -> None:
        for anvil_id in anvil_ids:
            self.__try_delete_container(f'{instance_id}-{anvil_id}')

        for daemon_id in daemon_ids:
            self.__try_delete_container(f'{instance_id}-{daemon_id}')

        self.__try_delete_volume(instance_id)

    def __try_delete_container(self, container_name: str) -> None:
        try:
            container: Container = self.__client.containers.get(container_name)
        except NotFound:
            return

        logger.info(f'deleting container {container.id} ({container.name})')
        try:
            try:
                container.kill()
            except APIError as api_error:
                # http conflict = container not running, which is fine
                if api_error.status_code != http.client.CONFLICT:
                    raise
            container.remove()
        except Exception as e:
            logger.opt(exception=e).error(f'failed to delete container {container.name} ({container.id})')

    def __try_delete_volume(self, volume_name: str) -> None:
        try:
            volume: Volume = self.__client.volumes.get(volume_name)
        except NotFound:
            return

        logger.info(f'deleting volume {volume.name} ({volume.id})')
        try:
            volume.remove()
        except Exception as e:
            logger.opt(exception=e).error(f'failed to delete volume {volume.name} ({volume.id})')
