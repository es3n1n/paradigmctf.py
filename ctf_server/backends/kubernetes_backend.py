import http.client
import shlex
import time
from typing import TYPE_CHECKING, Any

from kubernetes import config
from kubernetes.client import V1EnvVar
from kubernetes.client.api import core_v1_api
from kubernetes.client.exceptions import ApiException
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
    from kubernetes.client.models import V1Pod


class KubernetesBackend(Backend):
    def __init__(self, database: Database, kubeconfig: str) -> None:
        if kubeconfig == 'incluster':
            config.load_incluster_config()
        else:
            config.load_kube_config(kubeconfig)

        self.__core_v1 = core_v1_api.CoreV1Api()

        # note(es3n1n, 28.03.24): see docker backend ctor if you're wondering why we are doing this after the vars init
        super().__init__(database)

    def _launch_instance_impl(self, request: CreateInstanceRequest) -> UserData:
        instance_id = request['instance_id']

        anvil_containers, anvil_volumes = self.__get_anvil_containers_and_volumes(request)
        pod_manifest = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': instance_id,
                'labels': {
                    'app': 'anvil',
                    'category': 'blockchain',
                    'challenge': f'{request["challenge_name"]}-instance',
                    'team': request['team_id'],
                },
            },
            'spec': {
                'automountServiceAccountToken': False,
                'volumes': anvil_volumes,
                'containers': anvil_containers + self.__get_daemon_containers(request),
            },
        }

        api_response: V1Pod = self.__core_v1.create_namespaced_pod(namespace='default', body=pod_manifest)
        while True:
            api_response = self.__core_v1.read_namespaced_pod(
                name=pod_manifest['metadata']['name'],  # type: ignore[index]
                namespace='default',
            )
            if api_response.status.phase != 'Pending':
                break
            time.sleep(1)

        anvil_instances: dict[str, InstanceInfo] = {}
        for offset, anvil_id in enumerate(request.get('anvil_instances', {}).keys()):
            anvil_instances[anvil_id] = {
                'id': anvil_id,
                'ip': api_response.status.pod_ip,
                'port': 8545 + offset,
            }
            self._remap_extra_anvil_keys(anvil_instances[anvil_id], request['anvil_instances'][anvil_id])

            self._prepare_node(
                request['anvil_instances'][anvil_id],
                Web3(
                    Web3.HTTPProvider(f'http://{anvil_instances[anvil_id]["ip"]}:{anvil_instances[anvil_id]["port"]}')
                ),
            )

        daemon_instances: dict[str, InstanceInfo] = {}
        for daemon_id in request.get('daemon_instances', {}):
            daemon_instances[daemon_id] = {'id': daemon_id}

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

    def __get_anvil_containers_and_volumes(
        self, args: CreateInstanceRequest
    ) -> tuple[list[Any], list[dict[str, str | dict]]]:
        # Making sure we're using the same items list order in both things
        volumes: list[dict[str, str | dict]] = []
        containers: list[Any] = []

        for offset, (anvil_id, anvil_args) in enumerate(args.get('anvil_instances', {}).items()):
            volume_name = f'workdir-{offset}'
            volumes.append(
                {
                    'name': volume_name,
                    'emptyDir': {},
                }
            )
            containers.append(
                {
                    'name': anvil_id,
                    'image': anvil_args.get('image', DEFAULT_IMAGE),
                    'command': ['sh', '-c'],
                    'args': [
                        'while true; do anvil '
                        + ' '.join(
                            [shlex.quote(str(v)) for v in format_anvil_args(anvil_args, anvil_id, 8545 + offset)]
                        )
                        + '; sleep 1; done;'
                    ],
                    'volumeMounts': [
                        {
                            'mountPath': '/data',
                            'name': volume_name,
                        }
                    ],
                    'env': [V1EnvVar(name=k, value=v) for k, v in format_anvil_env(anvil_args).items()],
                }
            )

        return containers, volumes

    def __get_daemon_containers(self, args: CreateInstanceRequest) -> list[Any]:
        return [
            {
                'name': daemon_id,
                'image': daemon_args['image'],
                'env': [
                    {
                        'name': 'INSTANCE_ID',
                        'value': args['instance_id'],
                    }
                ],
            }
            for (daemon_id, daemon_args) in args.get('daemon_instances', {}).items()
        ]

    def kill_instance(self, instance_id: str) -> UserData | None:
        instance = self._database.unregister_instance(instance_id)
        if instance is None:
            return None

        self.__core_v1.delete_namespaced_pod(namespace='default', name=instance_id, grace_period_seconds=0)

        while True:
            try:
                self.__core_v1.read_namespaced_pod(
                    namespace='default',
                    name=instance_id,
                )
            except ApiException as e:
                if e.status == http.client.NOT_FOUND:
                    break

            time.sleep(0.5)

        return instance

    def _cleanup_instance(self, args: CreateInstanceRequest) -> None:
        instance_id = args['instance_id']
        logger.warning(f'cleaning up instance: {instance_id}')

        try:
            self.__core_v1.delete_namespaced_pod(
                namespace='default',
                name=instance_id,
                grace_period_seconds=0,
                propagation_policy='Background',
            )
        except ApiException as e:
            if e.status != http.client.NOT_FOUND:
                logger.opt(exception=e).error(f'cannot delete pod {instance_id} during cleanup')
                return

        # wait until the pod disappears so that a subsequent launch can reuse the name
        while True:
            try:
                self.__core_v1.read_namespaced_pod(name=instance_id, namespace='default')
                time.sleep(0.5)
            except ApiException as e:
                if e.status == http.client.NOT_FOUND:
                    break
                raise
