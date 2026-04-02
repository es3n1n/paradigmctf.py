from __future__ import annotations

import pytest

from ctf_server.anvil_proxy import proxy_batch, validate_request
from ctf_server.types import InstanceInfo


@pytest.fixture
def anyio_backend() -> str:
    return 'asyncio'


def _instance(extra: list[str] | None = None) -> InstanceInfo:
    return InstanceInfo(id='test', ip='127.0.0.1', port=8545, extra_allowed_methods=extra)


def _rpc(method: str, id_: int = 1) -> dict:
    return {'jsonrpc': '2.0', 'id': id_, 'method': method}


async def _unreachable(_: list[dict]) -> dict | list | None:
    raise AssertionError


class TestValidateRequest:
    def test_allowed_eth_method(self) -> None:
        assert validate_request(_rpc('eth_blockNumber'), _instance()) is None

    def test_allowed_web3_method(self) -> None:
        assert validate_request(_rpc('web3_clientVersion'), _instance()) is None

    def test_allowed_net_method(self) -> None:
        assert validate_request(_rpc('net_version'), _instance()) is None

    def test_disallowed_namespace(self) -> None:
        resp = validate_request(_rpc('debug_traceTransaction'), _instance())
        assert resp is not None
        assert resp['error']['message'] == 'forbidden jsonrpc method'

    def test_disallowed_method_eth_sign(self) -> None:
        resp = validate_request(_rpc('eth_sign'), _instance())
        assert resp is not None
        assert resp['error']['message'] == 'forbidden jsonrpc method'

    def test_disallowed_method_send_transaction(self) -> None:
        resp = validate_request(_rpc('eth_sendTransaction'), _instance())
        assert resp is not None
        assert resp['error']['message'] == 'forbidden jsonrpc method'

    def test_disallowed_method_send_transaction_sync(self) -> None:
        resp = validate_request(_rpc('eth_sendTransactionSync'), _instance())
        assert resp is not None
        assert resp['error']['message'] == 'forbidden jsonrpc method'

    def test_disallowed_method_send_unsigned(self) -> None:
        resp = validate_request(_rpc('eth_sendUnsignedTransaction'), _instance())
        assert resp is not None
        assert resp['error']['message'] == 'forbidden jsonrpc method'

    def test_disallowed_method_sign_typed_data(self) -> None:
        for method in ('eth_signTypedData', 'eth_signTypedData_v3', 'eth_signTypedData_v4'):
            resp = validate_request(_rpc(method), _instance())
            assert resp is not None, method
            assert resp['error']['message'] == 'forbidden jsonrpc method'

    def test_extra_allowed_overrides_namespace(self) -> None:
        inst = _instance(extra=['debug_traceTransaction'])
        assert validate_request(_rpc('debug_traceTransaction'), inst) is None

    def test_extra_allowed_overrides_disallowed(self) -> None:
        inst = _instance(extra=['eth_sendTransaction'])
        assert validate_request(_rpc('eth_sendTransaction'), inst) is None

    def test_missing_id(self) -> None:
        resp = validate_request({'method': 'eth_blockNumber'}, _instance())
        assert resp is not None
        assert resp['error']['message'] == 'invalid jsonrpc id'

    def test_non_string_method(self) -> None:
        resp = validate_request({'id': 1, 'method': 123}, _instance())
        assert resp is not None
        assert resp['error']['message'] == 'invalid jsonrpc method'

    def test_missing_method(self) -> None:
        resp = validate_request({'id': 1}, _instance())
        assert resp is not None
        assert resp['error']['message'] == 'invalid jsonrpc method'

    def test_non_dict_request(self) -> None:
        resp = validate_request('not a dict', _instance())  # type: ignore[arg-type]
        assert resp is not None
        assert resp['error']['message'] == 'expected json object'


class TestProxyBatch:
    @pytest.fixture
    def instance(self) -> InstanceInfo:
        return _instance()

    @staticmethod
    async def _echo_send(reqs: list[dict]) -> dict | list | None:
        return [{'jsonrpc': '2.0', 'id': req['id'], 'result': 'ok'} for req in reqs]

    @pytest.mark.anyio
    async def test_all_valid(self, instance: InstanceInfo) -> None:
        batch = [_rpc('eth_blockNumber', id_=1), _rpc('eth_chainId', id_=2)]
        result = await proxy_batch(batch, instance, self._echo_send)
        assert len(result) == len(batch)
        assert all(r.get('result') == 'ok' for r in result)

    @pytest.mark.anyio
    async def test_all_invalid(self, instance: InstanceInfo) -> None:
        batch = [_rpc('debug_foo', id_=1), _rpc('eth_sign', id_=2)]
        result = await proxy_batch(batch, instance, _unreachable)
        assert len(result) == len(batch)
        assert all('error' in r for r in result)

    @pytest.mark.anyio
    async def test_mixed_valid_and_invalid(self, instance: InstanceInfo) -> None:
        batch = [
            _rpc('eth_blockNumber', id_=1),  # valid
            _rpc('debug_foo', id_=2),  # invalid
            _rpc('eth_chainId', id_=3),  # valid
        ]
        result = await proxy_batch(batch, instance, self._echo_send)
        assert len(result) == len(batch)
        errors = [r for r in result if 'error' in r]
        successes = [r for r in result if 'result' in r]
        assert len(errors) == 1
        assert errors[0]['id'] == batch[1]['id']
        assert len(successes) == len(batch) - 1

    @pytest.mark.anyio
    async def test_empty_batch(self, instance: InstanceInfo) -> None:
        result = await proxy_batch([], instance, _unreachable)
        assert result == []

    @pytest.mark.anyio
    async def test_upstream_non_list_response(self, instance: InstanceInfo) -> None:
        batch = [_rpc('eth_blockNumber', id_=1)]

        async def _error_send(_: list[dict]) -> dict | list | None:
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32000, 'message': 'server error'}}

        result = await proxy_batch(batch, instance, _error_send)
        assert len(result) == 0

    @pytest.mark.anyio
    async def test_upstream_none_response(self, instance: InstanceInfo) -> None:
        batch = [_rpc('eth_blockNumber', id_=1)]

        async def _none_send(_: list[dict]) -> dict | list | None:
            return None

        result = await proxy_batch(batch, instance, _none_send)
        assert len(result) == 0

    @pytest.mark.anyio
    async def test_only_valid_requests_sent_upstream(self, instance: InstanceInfo) -> None:
        sent: list[list[dict]] = []

        async def _capture_send(reqs: list[dict]) -> dict | list | None:
            sent.append(reqs)
            return [{'jsonrpc': '2.0', 'id': req['id'], 'result': 'ok'} for req in reqs]

        batch = [
            _rpc('eth_blockNumber', id_=1),
            _rpc('eth_sign', id_=2),
            _rpc('eth_chainId', id_=3),
        ]
        await proxy_batch(batch, instance, _capture_send)

        assert len(sent) == 1
        forwarded_methods = [r['method'] for r in sent[0]]
        assert forwarded_methods == ['eth_blockNumber', 'eth_chainId']

    @pytest.mark.anyio
    async def test_duplicate_ids_passed_through(self, instance: InstanceInfo) -> None:
        batch = [_rpc('eth_blockNumber', id_=1), _rpc('eth_chainId', id_=1)]
        result = await proxy_batch(batch, instance, self._echo_send)
        assert len(result) == len(batch)
