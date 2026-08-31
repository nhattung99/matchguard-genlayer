# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
from datetime import datetime, timezone
import json

UserError = gl.vm.UserError

ZERO_ADDR = Address("0x0000000000000000000000000000000000000000")
VALID_SIDES = ("A", "B")
VALID_VERDICTS = ("NO_CHEAT", "CHEAT_CONFIRMED")
MIN_CONFIDENCE = 60

AWAITING_RESULT = "AWAITING_RESULT"
RESULT_DECLARED = "RESULT_DECLARED"
CHALLENGED = "CHALLENGED"
RESOLVED_UNCHALLENGED = "RESOLVED_UNCHALLENGED"
RESOLVED_NO_CHEAT = "RESOLVED_NO_CHEAT"
RESOLVED_CHEAT_CONFIRMED = "RESOLVED_CHEAT_CONFIRMED"
PAYOUT_FAILED = "PAYOUT_FAILED"
DISPUTED_LOW_CONFIDENCE = "DISPUTED_LOW_CONFIDENCE"
EXPIRED_REFUNDED = "EXPIRED_REFUNDED"


def _to_address(val) -> Address:
    if isinstance(val, Address):
        return val
    if isinstance(val, bytes):
        return Address("0x" + val.hex())
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str.startswith("0x"):
            val_str = "0x" + val_str
        return Address(val_str)
    if hasattr(val, "as_hex"):
        return val
    try:
        return Address(val)
    except Exception:
        return Address("0x" + bytes(val).hex())


def _addr_str(a) -> str:
    try:
        return a.as_hex.lower()
    except Exception:
        s = str(a).lower()
        if not s.startswith("0x") and len(s) == 40:
            return "0x" + s
        return s


def _same_addr(a, b) -> bool:
    return _addr_str(a) == _addr_str(b)


def _is_zero(a) -> bool:
    return _same_addr(a, ZERO_ADDR)


def _empty_urls():
    try:
        return DynArray[str]()
    except Exception:
        return []


def _urls_to_list(urls) -> list:
    out = []
    try:
        n = len(urls)
    except Exception:
        return out
    for i in range(n):
        out.append(str(urls[i]))
    return out


def _current_unix_timestamp() -> u256:
    """
    Verified GenVM timestamp API (AgentSLA / ClaimVerdict / BetSettle):
    gl.message.datetime is an ISO 8601 string. Parse with datetime.fromisoformat
    to Unix seconds. Do not use gl.block.timestamp.
    """
    if hasattr(gl, "message") and hasattr(gl.message, "datetime") and gl.message.datetime:
        dt_str = str(gl.message.datetime).replace("Z", "+00:00")
        try:
            return u256(int(datetime.fromisoformat(dt_str).timestamp()))
        except Exception as err:
            raise UserError("Invalid execution timestamp format from GenVM message: " + str(err))
    return u256(int(datetime.now(timezone.utc).timestamp()))


def _parse_verdict(raw) -> dict:
    if isinstance(raw, dict):
        data = raw
    else:
        cleaned = str(raw).strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) >= 2 and lines[0].startswith("```"):
                lines = lines[1:]
            if len(lines) >= 1 and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            data = json.loads(cleaned)
        except Exception as e:
            raise UserError("Invalid JSON returned by AI adjudicator: " + str(e))

    if not isinstance(data, dict):
        raise UserError("AI verdict response must be a JSON object")
    if "verdict" not in data or "confidence" not in data or "reason" not in data:
        raise UserError("Missing required keys (verdict, confidence, reason) in AI verdict")

    verdict = str(data["verdict"]).strip().upper().replace(" ", "_")
    if verdict not in VALID_VERDICTS:
        raise UserError("verdict must be NO_CHEAT or CHEAT_CONFIRMED — got: " + verdict)

    try:
        conf = int(data["confidence"])
    except Exception:
        raise UserError("confidence must be an integer 0-100")
    if conf < 0 or conf > 100:
        raise UserError("confidence out of bounds: " + str(conf))

    return {
        "verdict": verdict,
        "confidence": conf,
        "reason": str(data["reason"]),
    }


def _leader_payload(leader_res):
    if hasattr(leader_res, "value") and isinstance(leader_res.value, dict):
        return leader_res.value
    if hasattr(leader_res, "calldata") and isinstance(leader_res.calldata, dict):
        return leader_res.calldata
    if isinstance(leader_res, dict):
        return leader_res
    return None


def _extract_result(result) -> dict:
    payload = _leader_payload(result)
    if payload is None:
        raise UserError("Invalid nondet consensus result")
    return payload


def _require_http_url(url: str, kind: str) -> str:
    cleaned = str(url).strip()
    if not cleaned or not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        raise UserError("Invalid " + kind + " URL: must start with http:// or https://")
    return cleaned


@allow_storage
@dataclass
class Match:
    organizer: Address
    player_a: Address
    player_b: Address
    description: str
    prize_amount: bigint
    result_deadline: u256
    challenge_window_seconds: u256
    declared_winner: str
    result_declared_at: u256
    challenge_evidence_urls: DynArray[str]
    reference_urls: DynArray[str]
    status: str
    verdict: str
    verdict_reason: str
    confidence: u256
    settled: bool


class Contract(gl.Contract):
    owner: Address
    match_counter: bigint
    matches: TreeMap[str, Match]

    def __init__(self):
        self.owner = gl.message.sender_address
        self.match_counter = bigint(0)

    def _require_match(self, match_id: str) -> Match:
        if match_id not in self.matches:
            raise UserError("Match does not exist")
        return self.matches[match_id]

    def _is_player(self, m: Match, sender) -> bool:
        return _same_addr(sender, m.player_a) or _same_addr(sender, m.player_b)

    def _is_party(self, m: Match, sender) -> bool:
        return self._is_player(m, sender) or _same_addr(sender, m.organizer)

    def _try_transfer(self, recipient: Address, amount: bigint) -> None:
        if amount <= bigint(0):
            return
        gl.get_contract_at(recipient).emit_transfer(value=u256(amount))

    def _declared_winner_addr(self, m: Match) -> Address:
        if m.declared_winner == "A":
            return m.player_a
        if m.declared_winner == "B":
            return m.player_b
        raise UserError("No declared winner")

    def _other_player(self, m: Match) -> Address:
        if m.declared_winner == "A":
            return m.player_b
        if m.declared_winner == "B":
            return m.player_a
        raise UserError("No declared winner")

    # Studio GenVM rejects non-zero value on a plain @gl.public.write:
    # ValueError: called non-payable method `create_match` with non-zero value
    # (verified on BetSettle / RefundGuard — the older "payable does not exist" note is outdated)
    @gl.public.write.payable
    def create_match(
        self,
        player_a: Address,
        player_b: Address,
        description: str,
        result_deadline: u256,
        challenge_window_seconds: u256,
    ) -> str:
        prize = bigint(gl.message.value)
        if prize <= bigint(0):
            raise UserError("Must send GEN as prize (amount must be > 0)")
        if not description or len(description.strip()) == 0:
            raise UserError("Description cannot be empty")
        if len(description) > 2000:
            raise UserError("Description cannot exceed 2000 characters")
        player_a = _to_address(player_a)
        player_b = _to_address(player_b)
        if _is_zero(player_a) or _is_zero(player_b):
            raise UserError("player_a and player_b cannot be the zero address")
        if _same_addr(player_a, player_b):
            raise UserError("player_a and player_b must be different addresses")
        if u256(challenge_window_seconds) == u256(0):
            raise UserError("challenge_window_seconds must be > 0")

        match_id = str(self.match_counter)
        self.match_counter = self.match_counter + bigint(1)

        empty_urls = _empty_urls()
        self.matches[match_id] = Match(
            organizer=gl.message.sender_address,
            player_a=player_a,
            player_b=player_b,
            description=description.strip(),
            prize_amount=prize,
            result_deadline=u256(result_deadline),
            challenge_window_seconds=u256(challenge_window_seconds),
            declared_winner="",
            result_declared_at=u256(0),
            challenge_evidence_urls=empty_urls,
            reference_urls=empty_urls,
            status=AWAITING_RESULT,
            verdict="",
            verdict_reason="",
            confidence=u256(0),
            settled=False,
        )
        return match_id

    @gl.public.write
    def declare_result(self, match_id: str, winner_side: str) -> None:
        m = self._require_match(match_id)
        sender = gl.message.sender_address
        if not self._is_party(m, sender):
            raise UserError("Only players or organizer can declare result")
        if m.status != AWAITING_RESULT:
            raise UserError("Cannot declare result in status: " + m.status)
        if m.settled:
            raise UserError("Match already settled")
        side = str(winner_side).strip().upper()
        if side not in VALID_SIDES:
            raise UserError("winner_side must be 'A' or 'B'")
        if _current_unix_timestamp() > m.result_deadline:
            raise UserError("Result declaration deadline has passed")

        m.declared_winner = side
        m.result_declared_at = _current_unix_timestamp()
        m.status = RESULT_DECLARED
        self.matches[match_id] = m

    @gl.public.write
    def claim_expired_refund(self, match_id: str) -> None:
        """Organizer takes the prize back if nobody declared a result before the deadline."""
        m = self._require_match(match_id)
        if not _same_addr(gl.message.sender_address, m.organizer):
            raise UserError("Only organizer can claim expired refund")
        if m.status != AWAITING_RESULT:
            raise UserError("Can only claim refund if no result was declared")
        if m.settled:
            raise UserError("Match already settled")
        if _current_unix_timestamp() <= m.result_deadline:
            raise UserError("Result deadline has not passed yet")

        m.status = EXPIRED_REFUNDED
        m.settled = True
        self.matches[match_id] = m
        try:
            self._try_transfer(m.organizer, m.prize_amount)
        except Exception as e:
            m.status = PAYOUT_FAILED
            m.settled = False
            m.verdict_reason = "Expired refund failed: " + str(e)
            self.matches[match_id] = m

    @gl.public.write
    def challenge_result(self, match_id: str, evidence_urls: DynArray[str], reference_urls: DynArray[str]) -> None:
        m = self._require_match(match_id)
        sender = gl.message.sender_address
        if not self._is_player(m, sender):
            raise UserError("Only players can challenge the result")
        if m.status not in [RESULT_DECLARED, DISPUTED_LOW_CONFIDENCE]:
            raise UserError("Cannot challenge in status: " + m.status)
        if _current_unix_timestamp() > m.result_declared_at + m.challenge_window_seconds:
            raise UserError("Challenge window has closed")
        if len(evidence_urls) < 1:
            raise UserError("At least 1 evidence URL required")
        if len(reference_urls) < 2:
            raise UserError("At least 2 independent reference URLs required")

        cleaned_evidence = []
        for u in evidence_urls:
            cleaned_evidence.append(_require_http_url(u, "evidence"))

        cleaned_refs = []
        for u in reference_urls:
            cleaned_refs.append(_require_http_url(u, "reference"))

        m.challenge_evidence_urls = cleaned_evidence
        m.reference_urls = cleaned_refs
        m.status = CHALLENGED
        self.matches[match_id] = m

    @gl.public.write
    def finalize_unchallenged_payout(self, match_id: str) -> None:
        """Permissionless: anyone can call after the challenge window closes with no challenge."""
        m = self._require_match(match_id)
        if m.status != RESULT_DECLARED:
            raise UserError("Cannot finalize in status: " + m.status)
        if m.settled:
            raise UserError("Match already settled")
        if _current_unix_timestamp() <= m.result_declared_at + m.challenge_window_seconds:
            raise UserError("Challenge window has not closed yet")

        winner = self._declared_winner_addr(m)
        m.status = RESOLVED_UNCHALLENGED
        m.settled = True
        self.matches[match_id] = m
        try:
            self._try_transfer(winner, m.prize_amount)
        except Exception as e:
            m.status = PAYOUT_FAILED
            m.settled = False
            m.verdict_reason = "Unchallenged payout failed: " + str(e)
            self.matches[match_id] = m

    @gl.public.write
    def resolve_challenge(self, match_id: str) -> None:
        m = self._require_match(match_id)
        if m.status != CHALLENGED:
            raise UserError("Match not in CHALLENGED status: " + m.status)
        if m.settled:
            raise UserError("Match already settled")

        description = m.description
        declared_winner = m.declared_winner
        evidence_urls_list = _urls_to_list(m.challenge_evidence_urls)
        reference_urls_list = _urls_to_list(m.reference_urls)

        def leader_fn() -> dict:
            evidence_contents = []
            for url in evidence_urls_list:
                try:
                    res = gl.nondet.web.render(url)
                    evidence_contents.append("[" + url + "]: " + (res.body if hasattr(res, "body") else str(res)))
                except Exception:
                    raise UserError("Failed to fetch evidence URL: " + url)

            reference_contents = []
            for url in reference_urls_list:
                try:
                    res = gl.nondet.web.render(url)
                    reference_contents.append("[" + url + "]: " + (res.body if hasattr(res, "body") else str(res)))
                except Exception:
                    raise UserError("Failed to fetch reference URL: " + url)

            prompt = (
                "You are a neutral esports match adjudicator investigating a cheating accusation.\n"
                "Match description: \"" + description + "\"\n"
                "Declared winner: Side " + declared_winner + "\n"
                "Challenge evidence submitted against the declared winner: " + str(evidence_contents) + "\n"
                "Independent verification sources (prioritize these if they contradict the challenge evidence): "
                + str(reference_contents) + "\n\n"
                "Decide strictly one of two outcomes based on objective evidence:\n"
                "- \"NO_CHEAT\": independent sources do not confirm cheating; the declared result stands.\n"
                "- \"CHEAT_CONFIRMED\": independent sources confirm cheating by the declared winner.\n\n"
                "Return ONLY raw JSON, no markdown:\n"
                "{\"verdict\": \"NO_CHEAT\" | \"CHEAT_CONFIRMED\", \"confidence\": <0-100>, \"reason\": \"<short justification>\"}"
            )

            raw = gl.nondet.exec_prompt(prompt)
            return _parse_verdict(raw)

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            leader_val = _leader_payload(leader_res)
            if not isinstance(leader_val, dict) or "verdict" not in leader_val:
                return False
            try:
                my_res = leader_fn()
            except Exception:
                return False
            # Absolute equality on the 2 discrete verdicts — no percentage tolerance.
            # Same confidence branch so validators cannot split RESOLVED vs DISPUTED.
            if my_res["verdict"] != leader_val["verdict"]:
                return False
            try:
                leader_conf = int(leader_val.get("confidence", 0))
                my_conf = int(my_res.get("confidence", 0))
            except Exception:
                return False
            return (my_conf >= MIN_CONFIDENCE) == (leader_conf >= MIN_CONFIDENCE)

        result = _extract_result(gl.vm.run_nondet(leader_fn, validator_fn))
        verdict = str(result["verdict"]).strip().upper().replace(" ", "_")
        if verdict not in VALID_VERDICTS:
            raise UserError("Consensus returned invalid verdict: " + verdict)
        try:
            confidence = int(result["confidence"])
        except Exception:
            raise UserError("Consensus returned invalid confidence")
        reason = str(result.get("reason", ""))

        m.verdict = verdict
        m.confidence = u256(confidence)
        m.verdict_reason = reason

        if confidence < MIN_CONFIDENCE:
            m.status = DISPUTED_LOW_CONFIDENCE
            self.matches[match_id] = m
            return

        self._settle_from_verdict(match_id, m)

    def _settle_from_verdict(self, match_id: str, m: Match) -> None:
        if m.verdict == "CHEAT_CONFIRMED":
            payout_winner = self._other_player(m)
            new_status = RESOLVED_CHEAT_CONFIRMED
        elif m.verdict == "NO_CHEAT":
            payout_winner = self._declared_winner_addr(m)
            new_status = RESOLVED_NO_CHEAT
        else:
            raise UserError("No stored verdict to settle")

        try:
            self._try_transfer(payout_winner, m.prize_amount)
            m.settled = True
            m.status = new_status
        except Exception as e:
            m.status = PAYOUT_FAILED
            m.settled = False
            m.verdict_reason = m.verdict_reason + " (Payout failed: " + str(e) + ")"
        self.matches[match_id] = m

    def _retry_recipient_and_status(self, m: Match):
        """Pick payout recipient from stored verdict / declared winner. Does not re-run AI."""
        if m.verdict == "CHEAT_CONFIRMED":
            return self._other_player(m), RESOLVED_CHEAT_CONFIRMED
        if m.verdict == "NO_CHEAT":
            return self._declared_winner_addr(m), RESOLVED_NO_CHEAT
        if m.declared_winner in VALID_SIDES:
            # finalize_unchallenged_payout failed — no AI verdict, declared winner stands
            return self._declared_winner_addr(m), RESOLVED_UNCHALLENGED
        # claim_expired_refund failed — no result declared
        return m.organizer, EXPIRED_REFUNDED

    @gl.public.write
    def retry_resolution(self, match_id: str) -> None:
        """Retry payout using stored verdict/result. Does not re-run AI."""
        m = self._require_match(match_id)
        sender = gl.message.sender_address
        if not self._is_party(m, sender):
            raise UserError("Only players or organizer can retry")
        if m.status != PAYOUT_FAILED:
            raise UserError("Can only retry PAYOUT_FAILED matches")
        if m.settled:
            raise UserError("Match already settled")

        recipient, new_status = self._retry_recipient_and_status(m)
        try:
            self._try_transfer(recipient, m.prize_amount)
            m.settled = True
            m.status = new_status
        except Exception as e:
            m.verdict_reason = m.verdict_reason + " (Retry failed again: " + str(e) + ")"
        self.matches[match_id] = m

    def _match_dict(self, match_id: str, m: Match, full: bool) -> dict:
        row = {
            "match_id": match_id,
            "organizer": _addr_str(m.organizer),
            "player_a": _addr_str(m.player_a),
            "player_b": _addr_str(m.player_b),
            "description": m.description,
            "prize_amount": str(int(m.prize_amount)),
            "result_deadline": str(int(m.result_deadline)),
            "challenge_window_seconds": str(int(m.challenge_window_seconds)),
            "declared_winner": m.declared_winner,
            "result_declared_at": str(int(m.result_declared_at)),
            "status": m.status,
            "verdict": m.verdict,
            "verdict_reason": m.verdict_reason,
            "confidence": int(m.confidence),
            "settled": bool(m.settled),
        }
        if full:
            row["challenge_evidence_urls"] = _urls_to_list(m.challenge_evidence_urls)
            row["reference_urls"] = _urls_to_list(m.reference_urls)
        return row

    @gl.public.view
    def get_match(self, match_id: str) -> str:
        m = self._require_match(match_id)
        return json.dumps(self._match_dict(match_id, m, True))

    @gl.public.view
    def list_matches(self, status_filter: str) -> str:
        results = []
        n = int(self.match_counter)
        for i in range(n):
            mid = str(i)
            if mid in self.matches:
                m = self.matches[mid]
                if status_filter == "" or m.status == status_filter:
                    results.append(self._match_dict(mid, m, False))
        return json.dumps(results)

    @gl.public.view
    def get_count(self) -> int:
        return int(self.match_counter)

    @gl.public.view
    def get_owner(self) -> str:
        return _addr_str(self.owner)
