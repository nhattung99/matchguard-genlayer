"""Deterministic EthSend / EOA transfer mocks for MatchGuard gltest runs.

Patch gltest's wasi `_handle_gl_call` (not only vm._gl_call_hook) so every VM
instance sees the same EthSend behavior. A per-VM hook can miss the active VM
that gltest swaps in during deploy/write, which is what produced steward
failures on adjudication / retry / balance cases.
"""

_FORCE_TRANSFER_FAIL = False
_ORIGINAL_HANDLE = None
_PATCHED = False


def _handle_gl_call_with_ethsend(vm, request):
    global _FORCE_TRANSFER_FAIL, _ORIGINAL_HANDLE
    if isinstance(request, dict) and "EthSend" in request:
        if _FORCE_TRANSFER_FAIL or getattr(vm, "_matchguard_force_transfer_fail", False):
            raise Exception("Simulated native transfer execution failure")
        try:
            payload = request["EthSend"]
            value = int(payload.get("value", 0) if isinstance(payload, dict) else 0)
            dest = payload.get("to") if isinstance(payload, dict) else None
            if value and dest is not None and hasattr(vm, "_balances"):
                key = vm._to_bytes(dest) if hasattr(vm, "_to_bytes") else dest
                vm._balances[key] = vm._balances.get(key, 0) + value
        except Exception:
            pass
        return {"ok": None}
    if _ORIGINAL_HANDLE is not None:
        return _ORIGINAL_HANDLE(vm, request)
    return None


def install_wasi_ethsend_patch():
    """Idempotent module-level EthSend patch for the whole test process."""
    global _ORIGINAL_HANDLE, _PATCHED
    import gltest.direct.wasi_mock as wasi_mock

    if _PATCHED and getattr(wasi_mock, "_handle_gl_call", None) is _handle_gl_call_with_ethsend:
        return
    if not _PATCHED:
        _ORIGINAL_HANDLE = wasi_mock._handle_gl_call
    wasi_mock._handle_gl_call = _handle_gl_call_with_ethsend
    _PATCHED = True


def install_eth_send_handler(vm):
    """Keep a per-VM hook too (older gltest paths)."""
    install_wasi_ethsend_patch()
    if vm is None:
        return

    def hook(_active_vm, request):
        return _handle_gl_call_with_ethsend(_active_vm, request)

    setattr(vm, "_matchguard_force_transfer_fail", False)
    setattr(vm, "_gl_call_hook", hook)


def force_transfer_fail(monkeypatch, vm):
    """Force EthSend and _EOAProxy.emit_transfer to raise until restore_transfer()."""
    global _FORCE_TRANSFER_FAIL
    import gltest.direct.loader

    install_wasi_ethsend_patch()

    def failing_emit_transfer(self, value=None, **kwargs):
        raise Exception("Simulated native transfer execution failure")

    monkeypatch.setattr(gltest.direct.loader._EOAProxy, "emit_transfer", failing_emit_transfer)
    _FORCE_TRANSFER_FAIL = True
    if vm is not None:
        setattr(vm, "_matchguard_force_transfer_fail", True)
        install_eth_send_handler(vm)


def restore_transfer(vm):
    """Clear forced-fail so retry_resolution can settle."""
    global _FORCE_TRANSFER_FAIL
    install_wasi_ethsend_patch()
    _FORCE_TRANSFER_FAIL = False
    if vm is not None:
        setattr(vm, "_matchguard_force_transfer_fail", False)
        install_eth_send_handler(vm)
