import json
import re
import sys
import pytest

CONTRACT_PATH = "contracts/match_guard.py"

MID = "FACEIT-CS2-88421"
GAME = "Counter-Strike 2"
TAG_A = "s1mple"
TAG_B = "device"
PLAYED_AT = 1700000000
REPLAY_HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OFFICIAL = "https://www.faceit.com/en/cs2/room/" + MID
REPLAY = "https://www.faceit.com/en/cs2/room/" + MID + "/replay"
EVIDENCE = "https://www.faceit.com/en/anticheat/reports/" + MID
REF1 = "https://api.faceit.com/match/v2/match/" + MID
REF2 = "https://www.faceit.com/en/cs2/bracket/" + MID
WIKI_QUERY = "https://en.wikipedia.org/wiki/FACEIT?match=" + MID
WIKI_PATH = "https://en.wikipedia.org/wiki/" + MID
WIKI_GENERIC = "https://en.wikipedia.org/wiki/Cheating_in_online_games"
QUERY_ONLY = "https://www.faceit.com/en/cs2/room?match=" + MID
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
    if hasattr(account, "as_hex"):
        try:
            hx = str(account.as_hex).lower()
            if not hx.startswith("0x"):
                hx = "0x" + hx
            return hx
        except Exception:
            pass
    if isinstance(account, (bytes, bytearray)):
        return "0x" + bytes(account).hex()
    s = str(account).strip().lower()
    if s.startswith("0x"):
        return s
    # Address repr sometimes looks like b"...." — fall back to hex of raw bytes
    raw = getattr(account, "as_bytes", None) or getattr(account, "address", None)
    if isinstance(raw, (bytes, bytearray)):
        return "0x" + bytes(raw).hex()
    return s


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
        GAME,
        MID,
        TAG_A,
        TAG_B,
        PLAYED_AT,
        REPLAY_HASH,
    )
    _clear_value(vm)
    return match_id


def _declare(contract, vm, party, match_id, side="A", official=None, replay=None, replay_hash=None):
    vm.sender = party
    contract.declare_result(
        match_id,
        side,
        official or OFFICIAL,
        replay or REPLAY,
        replay_hash if replay_hash is not None else REPLAY_HASH,
    )


def _challenge(
    contract,
    vm,
    player,
    match_id,
    evidence=None,
    refs=None,
    claimed_match_id=None,
    claimed_tag=None,
    kind="ANTI_CHEAT",
):
    vm.sender = player
    contract.challenge_result(
        match_id,
        claimed_match_id or MID,
        claimed_tag or TAG_A,
        kind,
        evidence or [EVIDENCE],
        refs or [REF1, REF2],
    )


def _web_mocks(mapping):
    # gltest treats mock keys as regex; escape '?' in ?match= so WebRender hits the mock.
    return {re.escape(url): body for url, body in mapping.items()}


def _standard_web_no_cheat():
    return _web_mocks({
        OFFICIAL: "FACEIT match FACEIT-CS2-88421 official result: s1mple vs device, s1mple wins, no anti-cheat flag",
        REPLAY: "VOD for FACEIT-CS2-88421: both players visible, no wallhack artifacts",
        EVIDENCE: "Replay notes for FACEIT-CS2-88421: unusual flicks alleged, not confirmed",
        REF1: "VAC record for FACEIT-CS2-88421 participants: no ban",
        REF2: "Public listing FACEIT-CS2-88421: match played clean",
    })


def _standard_web_cheat():
    return _web_mocks({
        OFFICIAL: "FACEIT-CS2-88421 anti-cheat: s1mple account banned mid-match for wallhack",
        REPLAY: "VOD FACEIT-CS2-88421: declared winner tracking through walls for 40 seconds",
        EVIDENCE: "Replay FACEIT-CS2-88421: wallhack pattern on s1mple",
        REF1: "Official anti-cheat report FACEIT-CS2-88421: account banned for wallhack",
        REF2: "Caster overlay FACEIT-CS2-88421: aimbot pattern confirmed",
    })


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
        contract.declare_result(match_id, "A", OFFICIAL, REPLAY, REPLAY_HASH)
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
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [EVIDENCE], [REF1, REF2])
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
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [EVIDENCE], [REF1])
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [], [REF1, REF2])
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

    vm.sender = player_b
    with pytest.raises(Exception):
        contract.challenge_result(
            match_id,
            MID,
            TAG_A,
            "ANTI_CHEAT",
            ["https://www.faceit.com/en/anticheat/reports/" + MID + "/extra"],
            [
                "https://api.faceit.com/match/v2/match/" + MID + "/alt",
                "https://www.faceit.com/en/cs2/bracket/" + MID + "/alt",
            ],
        )
    assert _match(contract, match_id)["status"] == "DISPUTED_LOW_CONFIDENCE"
    assert _match(contract, match_id)["evidence_frozen"] is True


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
        contract.declare_result(match_id, "B", OFFICIAL, REPLAY, REPLAY_HASH)

    _challenge(contract, vm, player_b, match_id)
    vm.sender = player_a
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [EVIDENCE], [REF1, REF2])

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
        contract.create_match(
            player_a, player_a, "same players", FAR_FUTURE, LONG_WINDOW,
            GAME, MID, TAG_A, TAG_B, PLAYED_AT, REPLAY_HASH,
        )
    _clear_value(vm)

    vm.sender = organizer
    _set_value(vm, 0)
    with pytest.raises(Exception):
        contract.create_match(
            direct_accounts[2], direct_accounts[3], "empty prize", FAR_FUTURE, LONG_WINDOW,
            GAME, MID, TAG_A, TAG_B, PLAYED_AT, REPLAY_HASH,
        )
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
        contract.declare_result(match_id, "A", OFFICIAL, REPLAY, REPLAY_HASH)

    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = outsider
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [EVIDENCE], [REF1, REF2])


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


def _failing_transfer(monkeypatch, vm):
    """Force the next EthSend / emit_transfer to raise. Prefer restore_transfer() over
    monkeypatch.undo() so time warps and the default EthSend handler stay intact.
    """
    from transfer_mock import force_transfer_fail

    force_transfer_fail(monkeypatch, vm)


def _restore_transfer(vm):
    from transfer_mock import restore_transfer

    restore_transfer(vm)


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

    _failing_transfer(monkeypatch, vm)
    vm.sender = organizer
    contract.finalize_unchallenged_payout(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["settled"] is False
    assert "Unchallenged payout failed" in row["verdict_reason"]

    _restore_transfer(vm)
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

    _failing_transfer(monkeypatch, vm)
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
    assert row["payout_recipient"].lower() == _addr(player_a).lower()
    assert row["prize_amount"] == "2500"

    _restore_transfer(vm)
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

    _failing_transfer(monkeypatch, vm)
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
    assert row["payout_recipient"].lower() == _addr(player_b).lower()
    assert row["prize_amount"] == "1800"

    _restore_transfer(vm)
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

    _failing_transfer(monkeypatch, vm)
    vm.sender = organizer
    contract.claim_expired_refund(match_id)

    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["settled"] is False
    assert "Expired refund failed" in row["verdict_reason"]

    _restore_transfer(vm)
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


def test_challenge_rejects_http_unbound_and_hltv(direct_vm, direct_deploy, direct_accounts):
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
            MID,
            TAG_A,
            "ANTI_CHEAT",
            ["https://www.hltv.org/matches/237000"],
            [REF1, REF2],
        )
    with pytest.raises(Exception):
        contract.challenge_result(
            match_id,
            MID,
            TAG_A,
            "ANTI_CHEAT",
            [WIKI_QUERY],
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
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [EVIDENCE], [REF1, REF1])
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [REF1], [REF1, REF2])
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [OFFICIAL], [REF1, REF2])
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

    _failing_transfer(monkeypatch, vm)
    vm.sender = player_b
    contract.recover_unresolved_escrow(match_id)
    row = _match(contract, match_id)
    assert row["status"] == "PAYOUT_FAILED"
    assert row["verdict"] == "TIMEOUT_REFUND"
    assert row["settled"] is False

    _restore_transfer(vm)
    vm.sender = organizer
    contract.retry_resolution(match_id)
    row = _match(contract, match_id)
    assert row["status"] == "RESOLVED_TIMEOUT_REFUND"
    assert row["settled"] is True


def test_mismatch_match_id_and_participant_blocked(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = player_b
    with pytest.raises(Exception):
        _challenge(contract, vm, player_b, match_id, claimed_match_id="OTHER-MATCH-1")
    with pytest.raises(Exception):
        _challenge(contract, vm, player_b, match_id, claimed_tag="notAPlayer")
    assert _match(contract, match_id)["status"] == "RESULT_DECLARED"


def test_altered_hash_and_unbound_official_url_blocked(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    vm.sender = player_a
    with pytest.raises(Exception):
        contract.declare_result(
            match_id,
            "A",
            WIKI_QUERY,
            REPLAY,
            REPLAY_HASH,
        )
    with pytest.raises(Exception):
        contract.declare_result(
            match_id,
            "A",
            OFFICIAL,
            REPLAY,
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )
    assert _match(contract, match_id)["status"] == "AWAITING_RESULT"


def test_wikipedia_and_query_only_binding_rejected(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    vm.sender = player_a
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A", WIKI_QUERY, REPLAY, REPLAY_HASH)
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A", WIKI_PATH, REPLAY, REPLAY_HASH)
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A", QUERY_ONLY, REPLAY, REPLAY_HASH)
    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = player_b
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [WIKI_QUERY], [REF1, REF2])
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [WIKI_PATH], [REF1, REF2])
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [QUERY_ONLY], [REF1, REF2])
    row = _match(contract, match_id)
    assert row["status"] == "RESULT_DECLARED"
    assert row["platform_match_id"] == MID
    assert row["player_a_tag"] == TAG_A
    assert row["game_title"] == GAME
    assert row["official_result_url"] == OFFICIAL
    assert row["replay_content_hash"] == REPLAY_HASH


def test_critical_match_specific_evidence_model(direct_vm, direct_deploy, direct_accounts):
    """Wikipedia is never a match record. Identity and evidence identifiers must be committed."""
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    blocked = _parse(contract.get_blocked_hosts())
    assert "wikipedia.org" in blocked

    vm.sender = organizer
    _set_value(vm, 1000)
    with pytest.raises(Exception):
        contract.create_match(
            player_a, player_b, "desc", FAR_FUTURE, LONG_WINDOW, "CS", "", TAG_A, TAG_B, PLAYED_AT, REPLAY_HASH
        )
    with pytest.raises(Exception):
        contract.create_match(
            player_a, player_b, "desc", FAR_FUTURE, LONG_WINDOW, "", MID, TAG_A, TAG_B, PLAYED_AT, REPLAY_HASH
        )
    _clear_value(vm)

    match_id = _create(contract, vm, organizer, player_a, player_b)
    created = _match(contract, match_id)
    assert created["platform_match_id"] == MID
    assert created["game_title"] == GAME
    assert created["player_a_tag"] == TAG_A
    assert created["player_b_tag"] == TAG_B
    assert created["replay_content_hash"] == REPLAY_HASH
    assert created["official_result_url"] == ""
    assert created["replay_or_vod_url"] == ""

    vm.sender = player_a
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A", WIKI_GENERIC, REPLAY, REPLAY_HASH)
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A", WIKI_PATH, REPLAY, REPLAY_HASH)
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A", WIKI_QUERY, REPLAY, REPLAY_HASH)

    _declare(contract, vm, player_a, match_id, "A")
    declared = _match(contract, match_id)
    assert declared["official_result_url"] == OFFICIAL
    assert declared["replay_or_vod_url"] == REPLAY
    assert declared["platform_match_id"] == MID
    assert declared["game_title"] == GAME

    vm.sender = player_b
    with pytest.raises(Exception):
        contract.challenge_result(match_id, MID, TAG_A, "ANTI_CHEAT", [WIKI_GENERIC], [REF1, REF2])
    _challenge(contract, vm, player_b, match_id)
    challenged = _match(contract, match_id)
    assert challenged["evidence_frozen"] is True
    assert challenged["attestation_kind"] == "ANTI_CHEAT"
    assert challenged["accused_player_tag"] == TAG_A
    assert EVIDENCE in challenged["challenge_evidence_urls"]


def test_unallowlisted_issuer_rejected(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    hosts = _parse(contract.get_approved_hosts())
    assert "faceit.com" in hosts
    assert "matchguard-genlayer.vercel.app" in hosts
    assert "wikipedia.org" not in hosts
    assert "example.com" not in hosts

    match_id = _create(contract, vm, organizer, player_a, player_b)
    vm.sender = player_a
    fake = "https://evil.example/records/" + MID + "/official.html"
    with pytest.raises(Exception):
        contract.declare_result(match_id, "A", fake, REPLAY, REPLAY_HASH)
    _declare(contract, vm, player_a, match_id, "A")
    vm.sender = player_b
    with pytest.raises(Exception):
        contract.challenge_result(
            match_id, MID, TAG_A, "ANTI_CHEAT", [fake], [REF1, REF2]
        )
    assert _match(contract, match_id)["status"] == "RESULT_DECLARED"


def test_balance_conservation_no_cheat_and_cheat(direct_vm, direct_deploy, direct_accounts):
    organizer = direct_accounts[1]
    player_a = direct_accounts[2]
    player_b = direct_accounts[3]
    contract = direct_deploy(CONTRACT_PATH)
    vm = _active_vm(direct_vm)

    prize_clean = 900
    prize_cheat = 400
    id_clean = _create(contract, vm, organizer, player_a, player_b, prize=prize_clean)
    id_cheat = _create(contract, vm, organizer, player_a, player_b, prize=prize_cheat)
    assert int(_match(contract, id_clean)["prize_amount"]) == prize_clean
    assert int(_match(contract, id_cheat)["prize_amount"]) == prize_cheat

    _declare(contract, vm, player_a, id_clean, "A")
    _challenge(contract, vm, player_b, id_clean)
    sim_installMocks(
        vm,
        web=_standard_web_no_cheat(),
        llm={"verdict": "NO_CHEAT", "confidence": 88, "reason": "Clean match-specific records"},
    )
    vm.sender = player_a
    contract.resolve_challenge(id_clean)
    clean = _match(contract, id_clean)
    assert clean["status"] == "RESOLVED_NO_CHEAT"
    assert clean["settled"] is True
    assert clean["verdict"] == "NO_CHEAT"
    assert int(clean["prize_amount"]) == prize_clean
    assert clean["payout_recipient"].lower() == _addr(player_a).lower()

    _declare(contract, vm, player_a, id_cheat, "A")
    _challenge(contract, vm, player_b, id_cheat)
    sim_installMocks(
        vm,
        web=_standard_web_cheat(),
        llm={"verdict": "CHEAT_CONFIRMED", "confidence": 91, "reason": "Anti-cheat confirmed"},
    )
    vm.sender = player_b
    contract.resolve_challenge(id_cheat)
    cheat = _match(contract, id_cheat)
    assert cheat["status"] == "RESOLVED_CHEAT_CONFIRMED"
    assert cheat["settled"] is True
    assert cheat["verdict"] == "CHEAT_CONFIRMED"
    assert int(cheat["prize_amount"]) == prize_cheat
    assert cheat["payout_recipient"].lower() == _addr(player_b).lower()
    assert int(clean["prize_amount"]) + int(cheat["prize_amount"]) == prize_clean + prize_cheat
