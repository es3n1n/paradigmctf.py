from cheb3 import Connection
from requests import Session

from tests import compile_src_for


PORT = 31339
TEAM = 'test'

session = Session()


def test_api_mode() -> None:
    assert session.delete(f'http://localhost:{PORT}/v1/instance', params={'team_id': TEAM}).status_code == 200  # noqa: PLR2004

    response = session.put(f'http://localhost:{PORT}/v1/instance', json={'team_id': TEAM})
    assert response.status_code == 200, response.text  # noqa: PLR2004
    data = response.json()
    assert 'expires_at' in data
    assert 'expires_in_sec' in data
    assert 'rpc_endpoints' in data
    assert 'player_private_key' in data
    assert 'contracts' in data
    assert 'main' in data['rpc_endpoints']
    assert 'Hello' in data['contracts']

    response = session.get(f'http://localhost:{PORT}/v1/instance', params={'team_id': TEAM})
    assert response.status_code == 200  # noqa: PLR2004
    new_data = response.json()

    for k in ('player_private_key', 'contracts', 'rpc_endpoints'):
        assert new_data[k] == data[k], f'{k} mismatch'

    response = session.get(f'http://localhost:{PORT}/v1/pwn/flag', params={'team_id': TEAM, 'hello': 'world'})
    assert response.status_code == 400  # noqa: PLR2004
    flag_json = response.json()
    assert 'detail' in flag_json
    assert 'flag' not in flag_json

    # solve
    contracts = compile_src_for('hello', 'Hello.sol', solc_version='0.8.27')
    conn = Connection(data['rpc_endpoints']['main']['http'])
    acc = conn.account(data['player_private_key'])
    hello_abi, hello_bytecode = contracts['Hello']
    hello = conn.contract(
        signer=acc, address=data['contracts']['Hello']['address'], abi=hello_abi, bytecode=hello_bytecode
    )
    hello.functions.solve().send_transaction()

    # with invalid dynamic field
    response = session.get(f'http://localhost:{PORT}/v1/pwn/flag', params={'team_id': TEAM, 'hello': 'not world'})
    assert response.status_code == 400, response.text  # noqa: PLR2004
    assert 'flag' not in response.json()

    # with valid dynamic field
    response = session.get(f'http://localhost:{PORT}/v1/pwn/flag', params={'team_id': TEAM, 'hello': 'world'})
    assert response.status_code == 200  # noqa: PLR2004
    flag_json = response.json()
    assert 'flag' in flag_json
    assert flag_json['flag'] == 'cr3{paradigm_ctf_hello_api}'

    session.delete(f'http://localhost:{PORT}/v1/instance', params={'team_id': TEAM})
    response = session.get(f'http://localhost:{PORT}/v1/instance', params={'team_id': TEAM})
    assert response.status_code == 400, response.text  # noqa: PLR2004
