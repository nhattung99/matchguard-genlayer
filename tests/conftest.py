# conftest.py — keep EthSend / EOA payout deterministic under gltest direct mode.
import pytest

from transfer_mock import install_wasi_ethsend_patch, install_eth_send_handler, restore_transfer


@pytest.fixture(autouse=True)
def _matchguard_eth_send(direct_vm):
    """Patch wasi EthSend for every test; clear forced-fail before/after."""
    install_wasi_ethsend_patch()
    restore_transfer(direct_vm)
    try:
        from gltest.direct.loader import _get_active_vm

        active = _get_active_vm()
        if active is not None:
            install_eth_send_handler(active)
            restore_transfer(active)
    except Exception:
        pass
    yield
    restore_transfer(direct_vm)
