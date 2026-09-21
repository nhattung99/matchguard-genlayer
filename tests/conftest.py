# conftest.py — keep EthSend / EOA payout deterministic under gltest direct mode.
import pytest

from transfer_mock import install_eth_send_handler


@pytest.fixture(autouse=True)
def _matchguard_eth_send(direct_vm):
    """Every test gets a working EthSend path for `_EoaRecipient.emit_transfer`."""
    try:
        from gltest.direct.loader import _get_active_vm

        active = _get_active_vm() or direct_vm
    except Exception:
        active = direct_vm
    install_eth_send_handler(direct_vm)
    if active is not None and active is not direct_vm:
        install_eth_send_handler(active)
    yield
