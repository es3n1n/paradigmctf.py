from cheb3 import Connection

from . import EXTRA_METHODS_PWN, HELLO_PWN, compile_src_for


def test_challenge_hello() -> None:
    data = HELLO_PWN.launch(kill_if_exists=True)
    assert HELLO_PWN.get_pwn_flag('world') is None

    contracts = compile_src_for('hello', 'Hello.sol', solc_version='0.8.27')
    conn = Connection(data['http_endpoint'])
    acc = conn.account(data['private_key'])

    hello_abi, hello_bytecode = contracts['Hello']
    hello = conn.contract(signer=acc, address=data['contracts']['Hello'], abi=hello_abi, bytecode=hello_bytecode)
    hello.functions.solve().send_transaction()

    assert HELLO_PWN.get_pwn_flag('not world') is None
    assert HELLO_PWN.get_pwn_flag('world') == 'cr3{paradigm_ctf_hello_world}'


def test_extra_methods() -> None:
    extra_methods = EXTRA_METHODS_PWN.launch(kill_if_exists=False)
    hello = HELLO_PWN.launch(kill_if_exists=False)

    extra_methods_conn = Connection(extra_methods['http_endpoint'])
    hello_conn = Connection(hello['http_endpoint'])

    extra_res = extra_methods_conn.w3.provider.make_request(
        'debug_getRawReceipts',  # type: ignore[arg-type]
        ['latest'],
    )
    hello_res = hello_conn.w3.provider.make_request(
        'debug_getRawReceipts',  # type: ignore[arg-type]
        ['latest'],
    )

    assert hello_res == {'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32600, 'message': 'forbidden jsonrpc method'}}
    assert isinstance(extra_res['result'], list)
