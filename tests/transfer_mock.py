"""Deterministic EthSend / EOA transfer mocks for MatchGuard gltest runs."""


def install_eth_send_handler(vm):
    if vm is None:
        return

    def hook(_active_vm, request):
        if not isinstance(request, dict) or "EthSend" not in request:
            return None
        if getattr(_active_vm, "_matchguard_force_transfer_fail", False):
            raise Exception("Simulated native transfer execution failure")
        try:
            payload = request["EthSend"]
            value = int(payload.get("value", 0) if isinstance(payload, dict) else 0)
            dest = payload.get("to") if isinstance(payload, dict) else None
            if value and dest is not None and hasattr(_active_vm, "_balances"):
                key = _active_vm._to_bytes(dest) if hasattr(_active_vm, "_to_bytes") else dest
                _active_vm._balances[key] = _active_vm._balances.get(key, 0) + value
        except Exception:
            pass
        return {"ok": None}

    setattr(vm, "_matchguard_force_transfer_fail", False)
    setattr(vm, "_gl_call_hook", hook)


def _active_or(vm):
    try:
        from gltest.direct.loader import _get_active_vm

        active = _get_active_vm()
        if active is not None:
            return active
    except Exception:
        pass
    return vm


def force_transfer_fail(monkeypatch, vm):
    """Force EthSend / emit_transfer to raise until restore_transfer()."""
    import gltest.direct.loader

    def failing_emit_transfer(self, value=None, **kwargs):
        raise Exception("Simulated native transfer execution failure")

    monkeypatch.setattr(gltest.direct.loader._EOAProxy, "emit_transfer", failing_emit_transfer)
    targets = [vm, _active_or(vm)]
    seen = []
    for target in targets:
        if target is None or any(target is t for t in seen):
            continue
        seen.append(target)
        install_eth_send_handler(target)
        setattr(target, "_matchguard_force_transfer_fail", True)


def restore_transfer(vm):
    """Clear forced-fail so retry_resolution can settle."""
    targets = [vm, _active_or(vm)]
    seen = []
    for target in targets:
        if target is None or any(target is t for t in seen):
            continue
        seen.append(target)
        install_eth_send_handler(target)
        setattr(target, "_matchguard_force_transfer_fail", False)
