import json
import sys
import pytest

CONTRACT_PATH = "contracts/match_guard.py"

EVIDENCE = "https://en.wikipedia.org/wiki/Cheating_in_online_games"
REF1 = "https://en.wikipedia.org/wiki/Valve_Anti-Cheat"
REF2 = "https://en.wikipedia.org/wiki/Esports"
FAR_FUTURE = 4102444800  # 2100-01-01
PAST = 1
SHORT_WINDOW = 1
LONG_WINDOW = 86400


def _set_value(vm, amount):
    if hasattr(vm, "value"):
        try:
            vm.value = amount
        except Exception:
            pass
    if hasattr(vm, "_value"):
        vm._value = amount
    if hasattr(vm, "_refresh_gl_message"):
        vm._refresh_gl_message()


def _clear_value(vm):
    _set_value(vm, 0)


def _active_vm(direct_vm):
    try:
        from gltest.direct.loader import _get_active_vm
        return _get_active_vm() or direct_vm
    except Exception:
        return direct_vm


def sim_installMocks(vm, web=None, llm=None):
    """Install nondet mocks before every AI tx. Prefer sim_installMocks if present."""
    web = web or {}
    llm_payload = llm if isinstance(llm, str) or llm is None else json.dumps(llm)

    if hasattr(vm, "sim_installMocks"):
        vm.sim_installMocks({"web": web, "llm": llm_payload})
        return
    if hasattr(vm, "sim_install_mocks"):
        vm.sim_install_mocks({"web": web, "llm": llm_payload})
        return

    if hasattr(vm, "clear_mocks"):
        try:
            vm.clear_mocks()
        except Exception:
            pass
    for url, body in web.items():
        vm.mock_web(url, body)
    if llm_payload is not None:
        vm.mock_llm(".*", llm_payload)


def _parse(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _match(contract, match_id):
    return _parse(contract.get_match(match_id))


def _addr(account):
    try:
        return account.as_hex
    except Exception:
        return str(account)


def _create(
    contract,
    vm,
    organizer,
    player_a,
    player_b,
    description="CS2 Bo3 — Community Cup Round 1",
    prize=1000,
    result_deadline=FAR_FUTURE,
    challenge_window=LONG_WINDOW,
):
    vm.sender = organizer
    _set_value(vm, prize)
    match_id = contract.create_match(
        player_a,
        player_b,
        description,
        result_deadline,
        challenge_window,
    )
    _clear_value(vm)
    return match_id


def _declare(contract, vm, party, match_id, side="A"):
    vm.sender = party
    contract.declare_result(match_id, side)


def _challenge(contract, vm, player, match_id, evidence=None, refs=None):
    vm.sender = player
    contract.challenge_result(match_id, evidence or [EVIDENCE], refs or [REF1, REF2])


def _standard_web_no_cheat():
    return {
        EVIDENCE: "Replay clip claims unusual flick shots",
        REF1: "Official standings: match played clean, no VAC / anti-cheat flag",
        REF2: "Public VOD: both players visible, no wallhack artifacts",
    }


def _standard_web_cheat():
    return {
        EVIDENCE: "Replay: declared winner tracking through walls for 40 seconds",
        REF1: "Official anti-cheat report: account banned mid-match for wallhack",
        REF2: "Public VOD overlay: aimbot pattern confirmed by two casters",
    }


def _warp_now(monkeypatch, unix_ts):
    """Advance GenVM time. gl.message.datetime is pinned per tx; sleep does not move it."""
    from genlayer import u256

    def fake_now():
        return u256(int(unix_ts))

    hits = 0
    for _name, mod in list(sys.modules.items()):
        if callable(getattr(mod, "_current_unix_timestamp", None)):
            monkeypatch.setattr(mod, "_current_unix_timestamp", fake_now)
            hits += 1
    if hits < 1:
        raise RuntimeError("could not patch _current_unix_timestamp")


def _close_challenge_window(contract, match_id, monkeypatch):
    declared_at = int(_match(contract, match_id)["result_declared_at"])
    window = int(_match(contract, match_id)["challenge_window_seconds"])
    _warp_now(monkeypatch, declared_at + window + 1)


def test_happy_path_unchallenged_payout(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(
        contract, vm, organizer, player_a, player_b, prize=1000, challenge_window=SHORT_WINDOW
    )
    assert match_id == "0"
    row = _match(contract, match_id)
    assert row["status"] == "AWAITING_RESULT"
    assert row["prize_amount"] == "1000"
    assert row["settled"] is False

    _declare(contract, vm, player_a, match_id, "A")
    row = _match(contract, match_id)
    assert row["status"] == "RESULT_DECLARED"
    assert row["declared_winner"] == "A"

    _close_challenge_window(contract, match_id, monkeypatch)
    vm.sender = organizer
    contract.finalize_unchallenged_payout(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_UNCHALLENGED"
    assert row["settled"] is True
    assert row["verdict"] == ""


def test_happy_path_no_cheat_keeps_declared_winner(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=2500)
    _declare(contract, vm, organizer, match_id, "A")
    _challenge(contract, vm, player_b, match_id)

    sim_installMocks(
        vm,
        web=_standard_web_no_cheat(),
        llm={"verdict": "NO_CHEAT", "confidence": 91, "reason": "Independent sources do not confirm cheating"},
    )
    vm.sender = player_a
    contract.resolve_challenge(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_NO_CHEAT"
    assert row["verdict"] == "NO_CHEAT"
    assert row["confidence"] == 91
    assert row["settled"] is True


def test_happy_path_cheat_confirmed_reverses_winner(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=2500)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)

    sim_installMocks(
        vm,
        web=_standard_web_cheat(),
        llm={"verdict": "CHEAT_CONFIRMED", "confidence": 94, "reason": "Official anti-cheat and VOD confirm wallhack"},
    )
    vm.sender = player_b
    contract.resolve_challenge(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_CHEAT_CONFIRMED"
    assert row["verdict"] == "CHEAT_CONFIRMED"
    assert row["settled"] is True


def test_expired_no_result_organizer_refund(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(
        contract, vm, organizer, player_a, player_b, prize=500, result_deadline=PAST
    )
    vm.sender = organizer
    contract.claim_expired_refund(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "EXPIRED_REFUNDED"
    assert row["settled"] is True


def test_declare_after_deadline_blocked(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(
        contract, vm, organizer, player_a, player_b, result_deadline=PAST
    )
    vm.sender = player_a
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A")
    assert _match(contract, match_id)["status"] == "AWAITING_RESULT"


def test_challenge_after_window_closed_blocked(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(
        contract, vm, organizer, player_a, player_b, challenge_window=SHORT_WINDOW
    )
    _declare(contract, vm, player_a, match_id, "B")
    _close_challenge_window(contract, match_id, monkeypatch)

    vm.sender = player_a
    with pytest.raises(Exception):
        contract.challenge_result(match_id, [EVIDENCE], [REF1, REF2])
    assert _match(contract, match_id)["status"] == "RESULT_DECLARED"


def test_missing_reference_and_evidence_blocked(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = player_b
    with pytest.raises(Exception):
        contract.challenge_result(match_id, [EVIDENCE], [REF1])
    with pytest.raises(Exception):
        contract.challenge_result(match_id, [], [REF1, REF2])
    assert _match(contract, match_id)["status"] == "RESULT_DECLARED"


def test_low_confidence_disputed_then_rechallenge(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)

    sim_installMocks(
        vm,
        web=_standard_web_no_cheat(),
        llm={"verdict": "NO_CHEAT", "confidence": 41, "reason": "Sources conflict; not enough to settle"},
    )
    vm.sender = player_a
    contract.resolve_challenge(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "DISPUTED_LOW_CONFIDENCE"
    assert row["settled"] is False
    assert row["confidence"] == 41

    extra_ev = "https://en.wikipedia.org/wiki/Cheating_in_video_games"
    extra_r1 = "https://en.wikipedia.org/wiki/Counter-Strike_2"
    extra_r2 = "https://en.wikipedia.org/wiki/Fair_play"
    vm.sender = player_b
    contract.challenge_result(match_id, [extra_ev], [extra_r1, extra_r2])
    assert _match(contract, match_id)["status"] == "CHALLENGED"

    sim_installMocks(
        vm,
        web={
            extra_ev: "Clear anti-cheat log: no flags",
            extra_r1: "Official: match stands",
            extra_r2: "VOD: no wallhack artifacts",
        },
        llm={"verdict": "NO_CHEAT", "confidence": 88, "reason": "Updated independent sources confirm no cheat"},
    )
    vm.sender = player_a
    contract.resolve_challenge(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_NO_CHEAT"
    assert row["verdict"] == "NO_CHEAT"
    assert row["settled"] is True


def test_web_fail_and_invalid_json(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)

    sim_installMocks(vm, web={}, llm={"verdict": "NO_CHEAT", "confidence": 99, "reason": "should not run"})
    vm.sender = player_a
    with pytest.raises(Exception):
        contract.resolve_challenge(match_id)
    assert _match(contract, match_id)["status"] == "CHALLENGED"

    sim_installMocks(
        vm,
        web=_standard_web_no_cheat(),
        llm="this is not json {{{",
    )
    with pytest.raises(Exception):
        contract.resolve_challenge(match_id)
    row = _match(contract, match_id)
    assert row["status"] == "CHALLENGED"
    assert row["settled"] is False


def test_double_declare_challenge_finalize_resolve_blocked(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    outsider = direct_accounts[4]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=800)
    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = player_b
    with pytest.raises(Exception):
        contract.declare_result(match_id, "B")

    _challenge(contract, vm, player_b, match_id)
    vm.sender = player_a
    with pytest.raises(Exception):
        contract.challenge_result(match_id, [EVIDENCE], [REF1, REF2])

    vm.sender = outsider
    with pytest.raises(Exception):
        contract.finalize_unchallenged_payout(match_id)

    sim_installMocks(
        vm,
        web=_standard_web_no_cheat(),
        llm={"verdict": "NO_CHEAT", "confidence": 90, "reason": "No cheat confirmed"},
    )
    vm.sender = player_a
    contract.resolve_challenge(match_id)
    assert _match(contract, match_id)["status"] == "RESOLVED_NO_CHEAT"

    with pytest.raises(Exception):
        contract.resolve_challenge(match_id)


def test_same_players_and_zero_prize_blocked(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    vm.sender = organizer
    _set_value(vm, 1000)
    with pytest.raises(Exception):
        contract.create_match(player_a, player_a, "same players", FAR_FUTURE, LONG_WINDOW)
    _clear_value(vm)

    vm.sender = organizer
    _set_value(vm, 0)
    with pytest.raises(Exception):
        contract.create_match(direct_accounts[2], direct_accounts[3], "empty prize", FAR_FUTURE, LONG_WINDOW)
    _clear_value(vm)


def test_outsider_cannot_challenge_or_declare(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    outsider = direct_accounts[4]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    vm.sender = outsider
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A")

    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = outsider
    with pytest.raises(Exception):
        contract.challenge_result(match_id, [EVIDENCE], [REF1, REF2])


def test_expired_refund_before_deadline_blocked(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, result_deadline=FAR_FUTURE)
    vm.sender = organizer
    with pytest.raises(Exception):
        contract.claim_expired_refund(match_id)
    vm.sender = player_a
    with pytest.raises(Exception):
        contract.claim_expired_refund(match_id)


def _failing_transfer(monkeypatch):
    import gltest.direct.loader

    def failing_emit_transfer(self, value):
        raise Exception("Simulated native transfer execution failure")

    monkeypatch.setattr(gltest.direct.loader._EOAProxy, "emit_transfer", failing_emit_transfer)


def test_transfer_fail_unchallenged_then_retry(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(
        contract, vm, organizer, player_a, player_b, prize=2500, challenge_window=SHORT_WINDOW
    )
    _declare(contract, vm, player_a, match_id, "A")
    _close_challenge_window(contract, match_id, monkeypatch)

    _failing_transfer(monkeypatch)
    vm.sender = organizer
    contract.finalize_unchallenged_payout(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["settled"] is False
    assert "Unchallenged payout failed" in row["verdict_reason"]

    monkeypatch.undo()
    vm.sender = player_a
    contract.retry_resolution(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_UNCHALLENGED"
    assert row["settled"] is True


def test_transfer_fail_no_cheat_then_retry(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=2500)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)

    _failing_transfer(monkeypatch)
    sim_installMocks(
        vm,
        web=_standard_web_no_cheat(),
        llm={"verdict": "NO_CHEAT", "confidence": 97, "reason": "Independent sources do not confirm cheating"},
    )
    vm.sender = player_a
    contract.resolve_challenge(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["settled"] is False
    assert row["verdict"] == "NO_CHEAT"
    assert "Payout failed" in row["verdict_reason"]

    monkeypatch.undo()
    vm.sender = player_b
    contract.retry_resolution(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_NO_CHEAT"
    assert row["settled"] is True
    assert row["verdict"] == "NO_CHEAT"


def test_transfer_fail_cheat_confirmed_then_retry(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=1800)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)

    _failing_transfer(monkeypatch)
    sim_installMocks(
        vm,
        web=_standard_web_cheat(),
        llm={"verdict": "CHEAT_CONFIRMED", "confidence": 93, "reason": "Anti-cheat ban confirms wallhack"},
    )
    vm.sender = player_b
    contract.resolve_challenge(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["settled"] is False
    assert row["verdict"] == "CHEAT_CONFIRMED"

    monkeypatch.undo()
    vm.sender = organizer
    contract.retry_resolution(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_CHEAT_CONFIRMED"
    assert row["settled"] is True
    assert row["verdict"] == "CHEAT_CONFIRMED"


def test_transfer_fail_expired_refund_then_retry(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(
        contract, vm, organizer, player_a, player_b, prize=700, result_deadline=PAST
    )

    _failing_transfer(monkeypatch)
    vm.sender = organizer
    contract.claim_expired_refund(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["settled"] is False
    assert "Expired refund failed" in row["verdict_reason"]

    monkeypatch.undo()
    vm.sender = organizer
    contract.retry_resolution(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "EXPIRED_REFUNDED"
    assert row["settled"] is True


def test_retry_blocked_when_not_failed(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    vm.sender = organizer
    with pytest.raises(Exception):
        contract.retry_resolution(match_id)


def test_list_and_count(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    _create(contract, vm, organizer, player_a, player_b, prize=100)
    _create(contract, vm, organizer, player_a, player_b, prize=200)
    assert contract.get_count() == 2
    listed = _parse(contract.list_matches(""))
    assert len(listed) == 2
    waiting = _parse(contract.list_matches("AWAITING_RESULT"))
    assert len(waiting) == 2
    assert waiting[0]["prize_amount"] == "100"
    assert waiting[1]["prize_amount"] == "200"


def test_challenge_rejects_non_wikipedia_and_http(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = player_b
    with pytest.raises(Exception):
        contract.challenge_result(
            match_id,
            ["https://www.hltv.org/"],
            [REF1, REF2],
        )
    with pytest.raises(Exception):
        contract.challenge_result(
            match_id,
            ["http://en.wikipedia.org/wiki/Cheating_in_online_games"],
            [REF1, REF2],
        )
    assert _match(contract, match_id)["status"] == "RESULT_DECLARED"


def test_challenge_rejects_duplicate_and_overlapping_sources(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = player_b
    with pytest.raises(Exception):
        contract.challenge_result(match_id, [EVIDENCE], [REF1, REF1])
    with pytest.raises(Exception):
        contract.challenge_result(match_id, [REF1], [REF1, REF2])
    assert _match(contract, match_id)["status"] == "RESULT_DECLARED"


def test_timeout_recover_challenged_permissionless(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    outsider = direct_accounts[4]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=900, challenge_window=SHORT_WINDOW)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)

    vm.sender = outsider
    with pytest.raises(Exception):
        contract.recover_unresolved_escrow(match_id)

    challenged_at = int(_match(contract, match_id)["challenged_at"])
    window = int(_match(contract, match_id)["challenge_window_seconds"])
    _warp_now(monkeypatch, challenged_at + window + 1)
    vm.sender = outsider
    contract.recover_unresolved_escrow(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_TIMEOUT_REFUND"
    assert row["verdict"] == "TIMEOUT_REFUND"
    assert row["settled"] is True


def test_timeout_recover_disputed_low_confidence(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=400, challenge_window=SHORT_WINDOW)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)
    sim_installMocks(
        vm,
        web=_standard_web_no_cheat(),
        llm={"verdict": "NO_CHEAT", "confidence": 22, "reason": "Not enough to settle"},
    )
    vm.sender = player_a
    contract.resolve_challenge(match_id)
    assert _match(contract, match_id)["status"] == "DISPUTED_LOW_CONFIDENCE"

    challenged_at = int(_match(contract, match_id)["challenged_at"])
    window = int(_match(contract, match_id)["challenge_window_seconds"])
    _warp_now(monkeypatch, challenged_at + window + 1)
    vm.sender = organizer
    contract.recover_unresolved_escrow(match_id)
    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_TIMEOUT_REFUND"
    assert row["settled"] is True


def test_timeout_refund_transfer_fail_then_retry(direct_vm, direct_deploy, direct_accounts, monkeypatch):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b, prize=650, challenge_window=SHORT_WINDOW)
    _declare(contract, vm, player_a, match_id, "A")
    _challenge(contract, vm, player_b, match_id)
    challenged_at = int(_match(contract, match_id)["challenged_at"])
    window = int(_match(contract, match_id)["challenge_window_seconds"])
    _warp_now(monkeypatch, challenged_at + window + 1)

    _failing_transfer(monkeypatch)
    vm.sender = player_b
    contract.recover_unresolved_escrow(match_id)
    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["verdict"] == "TIMEOUT_REFUND"
    assert row["settled"] is False

    monkeypatch.undo()
    vm.sender = organizer
    contract.retry_resolution(match_id)
    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_TIMEOUT_REFUND"
    assert row["settled"] is True
