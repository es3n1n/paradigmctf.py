import builtins
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any

import aiohttp
import websockets
from fastapi import FastAPI, Request, WebSocket
from loguru import logger
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect
from websockets import WebSocketException

from .databases import Database
from .loaders import load_database
from .types import InstanceInfo
from .utils import worker


ALLOWED_NAMESPACES = ['web3', 'eth', 'net']
DISALLOWED_METHODS = [
    'eth_sign',
    'eth_signTransaction',
    'eth_signTypedData',
    'eth_signTypedData_v3',
    'eth_signTypedData_v4',
    'eth_sendTransaction',
    'eth_sendTransactionSync',
    'eth_sendUnsignedTransaction',
]


@dataclass
class Context:
    # note(es3n1n, 27.03.24): HACK: mypy won't know that we will initialize these within the lifespan
    session: aiohttp.ClientSession = None  # type: ignore[assignment]
    database: Database = None  # type: ignore[assignment]

    def setup(self) -> None:
        self.session = aiohttp.ClientSession()
        self.database = load_database()

    async def shutdown(self) -> None:
        if self.session is not None:
            await self.session.close()


context = Context()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    worker.setup('anvil_proxy')
    context.setup()
    yield
    await context.shutdown()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def jsonrpc_fail(id_: str | int | None, code: int, message: str) -> dict[str, str | dict[str, str | int] | Any]:
    return {
        'jsonrpc': '2.0',
        'id': id_,
        'error': {
            'code': code,
            'message': message,
        },
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(jsonrpc_fail(None, -32600, exc.detail), status_code=exc.status_code)


@app.api_route('/', methods=['GET', 'POST'])
async def root() -> dict:
    return jsonrpc_fail(None, -32600, 'Please use the full node url')


def validate_request(request: dict, instance_info: InstanceInfo) -> dict | None:
    if not isinstance(request, dict):
        return jsonrpc_fail(None, -32600, 'expected json object')

    request_id = request.get('id')
    request_method = request.get('method')

    if request_id is None:
        return jsonrpc_fail(None, -32600, 'invalid jsonrpc id')

    if not isinstance(request_method, str):
        return jsonrpc_fail(request_id, -32600, 'invalid jsonrpc method')

    denied = request_method.split('_')[0] not in ALLOWED_NAMESPACES or request_method in DISALLOWED_METHODS
    if denied and request_method not in (instance_info['extra_allowed_methods'] or []):
        return jsonrpc_fail(request_id, -32600, 'forbidden jsonrpc method')

    return None


async def send_request(
    anvil_instance: InstanceInfo, request_id: str | None, body: dict | list | str | int | None
) -> dict | None:
    instance_host = f'http://{anvil_instance["ip"]}:{anvil_instance["port"]}'
    try:
        async with context.session.post(instance_host, json=body) as resp:
            return await resp.json()
    except Exception as e:
        logger.opt(exception=e).error(f'failed to proxy anvil request to {anvil_instance}')
        return jsonrpc_fail(request_id, -32602, 'failed to proxy request to anvil instance')


async def proxy_request(anvil_instance: InstanceInfo, body: list | dict) -> dict | list | None:
    request_id = body.get('id') if isinstance(body, dict) else None

    if isinstance(body, list):
        responses = []
        for idx, req in enumerate(body):
            validation_error = validate_request(req, anvil_instance)
            responses.append(validation_error)

            if validation_error is not None:
                body[idx] = {
                    'jsonrpc': '2.0',
                    'id': idx,
                    'method': 'web3_clientVersion',
                }

        upstream_responses = await send_request(anvil_instance, request_id, body)
        for idx in range(len(responses)):
            if responses[idx] is None:
                if isinstance(upstream_responses, list):
                    responses[idx] = upstream_responses[idx]
                else:
                    responses[idx] = upstream_responses

        return responses

    if not isinstance(body, dict):
        return jsonrpc_fail(request_id, -32600, 'expected json object')

    validation_resp = validate_request(body, anvil_instance)
    if validation_resp is not None:
        return validation_resp
    return await send_request(anvil_instance, request_id, body)


@app.post('/{external_id}/{anvil_id}')
async def http_rpc(external_id: str, anvil_id: str, request: Request) -> dict | list | None:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return jsonrpc_fail(None, -32600, 'expected json body')

    user_data = context.database.get_instance_by_external_id(external_id)
    if user_data is None:
        return jsonrpc_fail(None, -32602, 'invalid rpc url, instance not found')

    anvil_instance = user_data.get('anvil_instances', {}).get(anvil_id, None)
    if anvil_instance is None:
        return jsonrpc_fail(None, -32602, 'invalid rpc url, chain not found')

    return await proxy_request(anvil_instance, body)


@app.websocket('/{external_id}/{anvil_id}/ws')
async def ws_rpc(external_id: str, anvil_id: str, client_ws: WebSocket) -> None:
    await client_ws.accept()

    user_data = context.database.get_instance_by_external_id(external_id)
    if user_data is None:
        await client_ws.send_json(jsonrpc_fail(None, -32602, 'invalid rpc url, instance not found'))
        return

    anvil_instance = user_data.get('anvil_instances', {}).get(anvil_id, None)
    if anvil_instance is None:
        await client_ws.send_json(jsonrpc_fail(None, -32602, 'invalid rpc url, chain not found'))
        return

    instance_host = f'ws://{anvil_instance["ip"]}:{anvil_instance["port"]}'

    try:
        async with websockets.connect(instance_host) as remote_ws:
            while True:
                raw_message = await client_ws.receive()
                if raw_message['type'] == 'websocket.disconnect':
                    break

                if raw_message['type'] != 'websocket.receive':
                    continue

                message_data: str = raw_message.get('text') or raw_message.get('bytes', b'').decode('utf-8')
                try:
                    json_msg = json.loads(message_data)
                except json.JSONDecodeError:
                    await client_ws.send_json(jsonrpc_fail(None, -32600, 'expected json body'))
                    continue

                if validation := validate_request(json_msg, anvil_instance):
                    await client_ws.send_json(validation)
                    continue

                await remote_ws.send(message_data)
                response = await remote_ws.recv()

                if isinstance(response, str):
                    response = response.encode()
                await client_ws.send_bytes(response)
    except (WebSocketDisconnect, WebSocketException, KeyError):  # KeyError for empty messages
        # fixme(es3n1n, 28.03.24): ugly exception handling
        with suppress(builtins.BaseException):
            await remote_ws.close()
        with suppress(builtins.BaseException):
            await client_ws.close()
