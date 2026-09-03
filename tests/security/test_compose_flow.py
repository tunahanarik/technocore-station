"""The approval chain: draft, sign, send - and everything that must refuse.

Three requests, and each one narrows what the next may do (ADR-0002 2). The
tests below are organised by what an attacker, a bug or an impatient user
would have to get past:

* an approval that was never given, has expired, has been used, or belongs to
  a different draft or session;
* a double click;
* the text or the target changing after it was approved;
* the protocol verdict changing after it was approved;
* a body that does not match what was signed;
* the write gate closing between two steps;
* the payload limits published by the live service;
* a lost response, an accepted write whose receipt cannot be read, and a
  network exception.

Nothing here contacts Technocore. The write client is always driven through
``httpx.MockTransport``, every seed and DID is a published TEST-ONLY fixture,
and the lobby is never a target (INV-05).
"""

from __future__ import annotations

import time

import httpx
import pytest
from sqlalchemy import Engine
from station_api.compose.approvals import (
    SEND_TOKEN_TTL_SECONDS,
    DraftStore,
    SendApproval,
    draft_digest,
)
from station_api.compose.nonce import NonceReserver
from station_api.compose.service import (
    MESSAGE_BODY_FIELDS,
    ComposeError,
    ComposeService,
)
from station_api.db.models import NonceState, WriteOutcomeValue
from station_api.security.tokens import SingleUseStore
from station_api.technocore.write_client import WriteOutcome
from technocore_conform import (
    MESSAGE_POLICY,
    canonical_message,
    is_canonical_signature,
    is_swept,
    sweep,
    verify_payload,
)

from tests.security.compose_fixtures import (
    TEST_ONLY_DID,
    TEST_ROOM,
    TEST_ROOM_ALT,
    ComposeHarness,
    StubIdentity,
    answering,
    build_harness,
    checked_technocore,
    raising,
)

pytestmark = pytest.mark.security

TEXT = "TEST ONLY - bu mesaj hicbir yere gitmez."


@pytest.fixture
def harness(engine: Engine) -> ComposeHarness:
    return build_harness(engine)


def _approve(harness: ComposeHarness, *, room: str = TEST_ROOM, text: str = TEXT):  # type: ignore[no-untyped-def]
    """Walk the chain to a send token."""
    draft = harness.service.draft(
        session_id=harness.session_id, room=room, text=text
    )
    signed = harness.service.sign(
        session_id=harness.session_id,
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    return draft, signed


# ---------------------------------------------------------------------------
# The happy path, and what it proves
# ---------------------------------------------------------------------------


def test_the_three_steps_publish_exactly_what_was_approved(
    harness: ComposeHarness,
) -> None:
    """The end-to-end property: shown == signed == sent.

    Every stage is compared against the same canonical bytes rather than
    against a restatement of them: the text the user was shown is the text in
    the canonical string, the canonical string is what the signature
    verifies over, and the body carries those exact characters.
    """
    draft, signed = _approve(harness)
    result = harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )

    assert result.outcome is WriteOutcome.ACCEPTED
    assert harness.writes.send_count == 1

    import json

    body = json.loads(harness.writes.requests[0].content)
    assert set(body) == set(MESSAGE_BODY_FIELDS)
    assert body["text"] == draft.swept_text
    assert body["did"] == TEST_ONLY_DID
    assert body["nonce"] == signed.nonce
    assert body["sig"] == signed.signature

    # The signature really covers those bytes, checked independently of the
    # code that produced it.
    payload = canonical_message(
        room=TEST_ROOM, nonce=body["nonce"], text=body["text"]
    )
    assert payload.canonical == signed.canonical
    verify_payload(payload, did=body["did"], signature=body["sig"])


def test_the_draft_step_signs_nothing_and_reserves_no_nonce(
    harness: ComposeHarness,
) -> None:
    """Step 1 is content approval only.

    A draft that reserved a nonce would burn one every time a user typed and
    changed their mind, and the counter is strictly increasing.
    """
    harness.service.draft(session_id=harness.session_id, room=TEST_ROOM, text=TEXT)

    assert harness.signer.signed == []
    assert harness.reserver.last_value(did=TEST_ONLY_DID, room=TEST_ROOM) == 0
    assert harness.writes.send_count == 0


def test_the_sign_step_sends_nothing(harness: ComposeHarness) -> None:
    """Signing is not publishing. That is the whole reason for two steps."""
    _approve(harness)

    assert harness.writes.send_count == 0


def test_the_swept_difference_is_shown_before_anything_is_signed(
    harness: ComposeHarness,
) -> None:
    """The user approves the stored form, not what they typed.

    The server verifies signatures over what it stored, so a user who
    approved the raw text would be approving something that never exists.
    """
    raw = "  merhaba​dunya  ‮"
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=raw
    )

    assert draft.changed_by_sweep is True
    assert draft.raw_text == raw
    assert draft.swept_text == sweep(raw, MESSAGE_POLICY)
    assert is_swept(draft.swept_text, MESSAGE_POLICY)
    assert draft.raw_chars != draft.swept_chars


def test_the_canonical_string_is_shown_verbatim_before_sending(
    harness: ComposeHarness,
) -> None:
    """The signature covers this string, not the JSON it travels in."""
    _, signed = _approve(harness)

    assert signed.canonical == f"{TEST_ROOM}|{signed.nonce}|{TEXT}"
    assert is_canonical_signature(signed.signature)


# ---------------------------------------------------------------------------
# The gate re-runs at every step
# ---------------------------------------------------------------------------


def test_every_step_re_runs_the_write_gate(harness: ComposeHarness) -> None:
    """Not once at the start. Every time.

    The state can change between two of these requests, and only the server
    is in a position to notice. A disabled button is not a control.
    """
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )
    assert harness.identity.gate_calls == 1

    signed = harness.service.sign(
        session_id=harness.session_id,
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    assert harness.identity.gate_calls == 2

    harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )
    assert harness.identity.gate_calls == 3


#: Each precondition of the gate, paired with the check key it blocks on.
#: Written out rather than derived so a check that quietly stopped blocking
#: would fail here instead of disappearing from the parametrisation.
GATE_PRECONDITIONS = [
    ("has_identity", "identity_present"),
    ("vault_present", "vault_present"),
    ("recovery_verified", "recovery_verified"),
    ("conformance_verified", "conformance_verified"),
    ("manifest_current", "manifest_current"),
]


@pytest.mark.parametrize(("precondition", "blocking_key"), GATE_PRECONDITIONS)
def test_a_closed_gate_refuses_the_draft(
    engine: Engine, precondition: str, blocking_key: str
) -> None:
    """Each precondition, on its own, is enough to refuse."""
    identity = StubIdentity()
    identity.close_gate(**{precondition: False})
    harness = build_harness(engine, identity=identity)

    with pytest.raises(ComposeError) as caught:
        harness.service.draft(
            session_id=harness.session_id, room=TEST_ROOM, text=TEXT
        )

    assert caught.value.reason == "write_gate_closed"
    assert blocking_key in str(caught.value)


def test_the_gate_preconditions_are_the_whole_gate() -> None:
    """The list above must not fall behind the gate it parametrises.

    A new check added to the write gate and not added here would be a
    precondition nothing proves the composer honours.
    """
    from station_api.identity.write_gate import WriteGateInput, evaluate

    every_key = {
        check.key
        for check in evaluate(
            WriteGateInput(
                has_identity=False,
                identity_revoked=True,
                vault_present=False,
                recovery_verified=False,
            )
        ).checks
    }
    covered = {key for _, key in GATE_PRECONDITIONS}

    # `identity_not_revoked` has its own test below, because flipping it
    # needs a different input field than the one that names it.
    assert every_key - covered == {"identity_not_revoked"}


def test_a_revoked_identity_between_draft_and_sign_refuses_the_signature(
    harness: ComposeHarness,
) -> None:
    """Revocation must take effect on the next request, not the next launch."""
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )
    harness.identity.close_gate(identity_revoked=True)

    with pytest.raises(ComposeError) as caught:
        harness.service.sign(
            session_id=harness.session_id,
            draft_id=draft.draft_id,
            confirmed_digest=draft.draft_digest,
            vault_passphrase=None,
        )

    assert caught.value.reason == "write_gate_closed"
    assert harness.signer.signed == []


def test_a_gate_that_closes_between_sign_and_send_stops_the_write(
    harness: ComposeHarness,
) -> None:
    """A valid approval is not a licence once a precondition has gone.

    The nonce is burnt anyway - the counter only goes forward - but it is
    recorded as never sent, and nothing leaves the process.
    """
    _, signed = _approve(harness)
    harness.identity.close_gate(recovery_verified=False)

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    assert caught.value.reason == "write_gate_closed"
    assert harness.writes.send_count == 0

    state, outcome = _state_of_last_nonce(harness)
    assert state == NonceState.CANCELLED.value
    assert outcome == WriteOutcomeValue.NOT_SENT.value


def _tamper(harness: ComposeHarness, token: str, **changes: str) -> None:
    """Rewrite a stored approval in place.

    Every bug this guards against has the same shape: the send path acting on
    an approval whose fields no longer describe what was signed. Editing the
    stored approval reproduces that directly, without having to invent a
    plausible way for it to happen.
    """
    from dataclasses import replace

    store = harness.service._approvals
    entry = store._tokens[token]
    store._tokens[token] = replace(
        entry, payload=replace(entry.payload, **changes)
    )


def _state_of_last_nonce(harness: ComposeHarness) -> tuple[str, str]:
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from station_api.db.models import MessageNonceReservation

    engine = harness.reserver._engine
    with Session(engine) as session:
        row = session.scalars(
            select(MessageNonceReservation).order_by(
                MessageNonceReservation.nonce_value.desc()
            )
        ).first()
        assert row is not None
        return row.state, row.outcome


# ---------------------------------------------------------------------------
# Approvals: missing, expired, reused, foreign, cross-draft
# ---------------------------------------------------------------------------


def test_sending_without_an_approval_is_refused(harness: ComposeHarness) -> None:
    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token="TEST-ONLY-never-issued"
        )

    assert caught.value.reason == "approval_invalid"
    assert harness.writes.send_count == 0


def test_an_expired_approval_is_refused(engine: Engine) -> None:
    """Three minutes is long enough to read and decide, and no longer.

    A forgotten approval must not still be armed hours later. The clock is
    injected so the expiry is asserted rather than waited for.
    """
    ticks = [0.0]
    approvals: SingleUseStore[SendApproval] = SingleUseStore(
        ttl_seconds=SEND_TOKEN_TTL_SECONDS, clock=lambda: ticks[0]
    )
    harness = build_harness(engine)
    service = ComposeService(
        identity=harness.identity,
        technocore=harness.technocore,
        reserver=harness.reserver,
        signer=harness.signer,
        write_client=harness.writes.client,
        approvals=approvals,
    )

    draft = service.draft(session_id=harness.session_id, room=TEST_ROOM, text=TEXT)
    signed = service.sign(
        session_id=harness.session_id,
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    assert signed.expires_in_seconds == SEND_TOKEN_TTL_SECONDS

    ticks[0] = SEND_TOKEN_TTL_SECONDS + 1

    with pytest.raises(ComposeError) as caught:
        service.send(session_id=harness.session_id, send_token=signed.send_token)

    assert caught.value.reason == "approval_invalid"
    assert harness.writes.send_count == 0


def test_the_approval_ttl_is_the_documented_three_minutes() -> None:
    """Pinned, because the number is a decision (ADR-0002 2), not a default."""
    assert SEND_TOKEN_TTL_SECONDS == 180


def test_a_reused_approval_is_refused(harness: ComposeHarness) -> None:
    """Single use. The second attempt is not a second message."""
    _, signed = _approve(harness)

    first = harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )
    assert first.outcome is WriteOutcome.ACCEPTED

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    assert caught.value.reason == "approval_invalid"
    assert harness.writes.send_count == 1


def test_a_double_click_sends_exactly_once(harness: ComposeHarness) -> None:
    """The realistic race, run as a race.

    Two threads present the same approval at the same moment. The token is
    popped under a lock together with its lookup, so one wins and the other
    finds nothing - and exactly one request leaves the process.
    """
    import threading

    _, signed = _approve(harness)

    outcomes: list[object] = []
    barrier = threading.Barrier(2)

    def click() -> None:
        barrier.wait()
        try:
            outcomes.append(
                harness.service.send(
                    session_id=harness.session_id, send_token=signed.send_token
                )
            )
        except ComposeError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=click) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert harness.writes.send_count == 1, "a double click published twice"
    assert sum(isinstance(item, ComposeError) for item in outcomes) == 1


def test_an_approval_from_another_session_is_refused(
    harness: ComposeHarness,
) -> None:
    """The approval belongs to the browser session that read the text."""
    _, signed = _approve(harness)

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id="TEST-ONLY-other-session", send_token=signed.send_token
        )

    assert caught.value.reason == "approval_foreign_session"
    assert harness.writes.send_count == 0


def test_a_draft_from_another_session_cannot_be_signed(
    harness: ComposeHarness,
) -> None:
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )

    with pytest.raises(ComposeError) as caught:
        harness.service.sign(
            session_id="TEST-ONLY-other-session",
            draft_id=draft.draft_id,
            confirmed_digest=draft.draft_digest,
            vault_passphrase=None,
        )

    assert caught.value.reason == "draft_missing"


def test_a_digest_from_a_different_draft_is_refused(
    harness: ComposeHarness,
) -> None:
    """An approval for one piece of content cannot sign another.

    Two drafts exist; the second one's digest is presented against the
    first one's id. Both are genuine, and the pairing is not.
    """
    first = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )
    second = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM_ALT, text="TEST ONLY - baska"
    )

    with pytest.raises(ComposeError) as caught:
        harness.service.sign(
            session_id=harness.session_id,
            draft_id=first.draft_id,
            confirmed_digest=second.draft_digest,
            vault_passphrase=None,
        )

    assert caught.value.reason == "draft_digest_mismatch"
    assert harness.signer.signed == []


def test_an_expired_draft_cannot_be_signed(engine: Engine) -> None:
    ticks = [0.0]
    harness = build_harness(engine)
    service = ComposeService(
        identity=harness.identity,
        technocore=harness.technocore,
        reserver=harness.reserver,
        signer=harness.signer,
        write_client=harness.writes.client,
        drafts=DraftStore(ttl_seconds=180, clock=lambda: ticks[0]),
    )

    draft = service.draft(session_id=harness.session_id, room=TEST_ROOM, text=TEXT)
    ticks[0] = 181

    with pytest.raises(ComposeError) as caught:
        service.sign(
            session_id=harness.session_id,
            draft_id=draft.draft_id,
            confirmed_digest=draft.draft_digest,
            vault_passphrase=None,
        )

    assert caught.value.reason == "draft_missing"


def test_revoking_the_identity_drops_its_pending_approvals(
    harness: ComposeHarness,
) -> None:
    """A capability signed by a destroyed key does not wait out its TTL.

    Belt and braces: revocation closes the gate and ``send`` re-compares the
    DID, so the approval was already refused twice over. Dropping it is about
    not leaving one lying around at all.
    """
    _, signed = _approve(harness)

    harness.service.forget_identity(TEST_ONLY_DID)

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    assert caught.value.reason == "approval_invalid"
    assert harness.writes.send_count == 0


def test_ending_a_session_forgets_its_drafts_and_approvals(
    harness: ComposeHarness,
) -> None:
    """An approval outliving its session is a capability with no owner."""
    draft, signed = _approve(harness)

    harness.service.forget_session(harness.session_id)

    with pytest.raises(ComposeError):
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )
    with pytest.raises(ComposeError):
        harness.service.sign(
            session_id=harness.session_id,
            draft_id=draft.draft_id,
            confirmed_digest=draft.draft_digest,
            vault_passphrase=None,
        )
    assert harness.writes.send_count == 0


# ---------------------------------------------------------------------------
# Content and target changes invalidate the approval
# ---------------------------------------------------------------------------


def test_changing_the_text_changes_the_digest(harness: ComposeHarness) -> None:
    """An old approval cannot sign new content (ADR-0002 2)."""
    original = draft_digest(room=TEST_ROOM, swept_text=TEXT)
    edited = draft_digest(room=TEST_ROOM, swept_text=TEXT + " edited")

    assert original != edited

    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )
    with pytest.raises(ComposeError) as caught:
        harness.service.sign(
            session_id=harness.session_id,
            draft_id=draft.draft_id,
            confirmed_digest=edited,
            vault_passphrase=None,
        )

    assert caught.value.reason == "draft_digest_mismatch"


def test_changing_the_room_changes_the_digest() -> None:
    """The target is part of what was approved, and of what is signed.

    A signature over ``room|nonce|text`` is only valid for that room, so an
    approval that survived a room change would produce a refused write at
    best and a message in the wrong public room at worst.
    """
    assert draft_digest(room=TEST_ROOM, swept_text=TEXT) != draft_digest(
        room=TEST_ROOM_ALT, swept_text=TEXT
    )


def test_a_text_that_sweeps_to_the_same_bytes_has_the_same_digest() -> None:
    """The mirror: the digest is over the *stored* form, not the typed one.

    Two different keystrokes that produce identical stored bytes are the
    same approval, because they are the same message.
    """
    raw_a = "  merhaba  "
    raw_b = "	merhaba	"
    assert sweep(raw_a, MESSAGE_POLICY) == sweep(raw_b, MESSAGE_POLICY)
    assert draft_digest(
        room=TEST_ROOM, swept_text=sweep(raw_a, MESSAGE_POLICY)
    ) == draft_digest(room=TEST_ROOM, swept_text=sweep(raw_b, MESSAGE_POLICY))


# ---------------------------------------------------------------------------
# Stale verdict
# ---------------------------------------------------------------------------


def test_a_new_manifest_check_invalidates_a_pending_approval(
    harness: ComposeHarness,
) -> None:
    """The approval is bound to the evidence the user saw.

    Re-running the check produces new evidence, whose result the user has
    not seen. Even a check that finds the same protocol unchanged is a new
    verdict, and this is the fail-closed reading of ADR-0002 2.
    """
    _, signed = _approve(harness)
    before = harness.technocore.status().verdict_id
    assert before

    harness.technocore.refresh()
    assert harness.technocore.status().verdict_id != before

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    assert caught.value.reason == "stale_verdict"
    assert harness.writes.send_count == 0


def test_a_verdict_that_stops_being_current_invalidates_the_approval(
    engine: Engine,
) -> None:
    """Drift after signing must not let a three-minute-old approval fire."""
    live = checked_technocore(engine)
    harness = build_harness(engine, technocore=live)
    _, signed = _approve(harness)

    # The next check finds nothing: every required document 503s.
    from station_api.technocore.client import ReadOnlyTechnocoreClient

    live._client = ReadOnlyTechnocoreClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        sleep=lambda _: None,
    )
    live.refresh()
    assert live.status().manifest_current is False

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    # The gate closes first, which is the stricter of the two refusals.
    assert caught.value.reason in {"write_gate_closed", "stale_verdict"}
    assert harness.writes.send_count == 0


def test_a_never_checked_verdict_has_no_identity_to_bind_to(
    engine: Engine,
) -> None:
    """An empty verdict id can never match a stored one.

    Which means an approval minted while the check was unavailable is dead
    on arrival rather than universally valid.
    """
    from station_api.technocore.service import TechnocoreService

    fresh = TechnocoreService(engine=engine)
    assert fresh.status().verdict_id == ""


# ---------------------------------------------------------------------------
# The body is re-validated against what was signed
# ---------------------------------------------------------------------------


def test_a_body_that_drifted_from_the_signed_bytes_is_not_sent(
    harness: ComposeHarness,
) -> None:
    """The canonical digest is the check, and it is over the signed bytes.

    Simulated by tampering with the stored approval - which is the shape any
    such bug would take: the send path rebuilding a body that is no longer
    the one the signature covers.
    """
    _, signed = _approve(harness)
    _tamper(harness, signed.send_token, swept_text=TEXT + " tampered")

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    assert caught.value.reason == "canonical_mismatch"
    assert harness.writes.send_count == 0


def test_a_signature_that_does_not_verify_is_never_sent(
    harness: ComposeHarness,
) -> None:
    """A fixed-length pre-check does not stand in for verification.

    The forged value below is exactly 86 characters and canonically shaped,
    so every length and pattern check passes. Only a real Ed25519
    verification catches it, and the send path performs one.
    """
    _, signed = _approve(harness)
    forged = "A" * 85 + "Q"
    assert is_canonical_signature(forged)
    assert len(forged) == len(signed.signature)

    _tamper(harness, signed.send_token, signature=forged)

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    assert caught.value.reason == "signature_invalid"
    assert harness.writes.send_count == 0


def test_a_wrong_key_produces_a_signature_the_send_path_refuses(
    engine: Engine,
) -> None:
    """The signer and the DID must agree, and disagreement is caught here.

    Not at the server, as a 403 with no explanation, after the user approved
    a publication.
    """
    from tests.conftest import TEST_ONLY_SEED_HEX_ALT
    from tests.security.compose_fixtures import TestOnlySigner

    harness = build_harness(engine)
    harness.service._signer = TestOnlySigner(
        bytes.fromhex(TEST_ONLY_SEED_HEX_ALT)
    )

    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )
    with pytest.raises(ComposeError) as caught:
        harness.service.sign(
            session_id=harness.session_id,
            draft_id=draft.draft_id,
            confirmed_digest=draft.draft_digest,
            vault_passphrase=None,
        )

    assert caught.value.reason == "signature_invalid"
    assert harness.writes.send_count == 0


def test_the_identity_changing_after_signing_invalidates_the_approval(
    harness: ComposeHarness,
) -> None:
    _, signed = _approve(harness)
    harness.identity.did = "did:key:z6MkTESTONLYdifferentidentity000000000000000000000"

    with pytest.raises(ComposeError) as caught:
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )

    assert caught.value.reason == "identity_changed"
    assert harness.writes.send_count == 0


def test_the_body_carries_no_from_field(harness: ComposeHarness) -> None:
    """The reference ignores ``from`` on the signed lane.

    Sending it would add a field the signature does not cover and nothing
    validates - the exact shape of a claim that looks stronger than it is.
    """
    _, signed = _approve(harness)
    harness.service.send(session_id=harness.session_id, send_token=signed.send_token)

    import json

    assert "from" not in json.loads(harness.writes.requests[0].content)


# ---------------------------------------------------------------------------
# Payload limits, read from the live check
# ---------------------------------------------------------------------------


def test_the_limits_come_from_the_live_projection(harness: ComposeHarness) -> None:
    """Not hardcoded (charter 14.4, INV-12).

    The value reported to the user is the same one ``effective_payload_limits``
    computes from the document that was actually fetched.
    """
    projection = harness.technocore.status().projection
    assert projection is not None
    effective = projection.effective_payload_limits["text"]

    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )

    assert draft.max_chars == effective.maximum
    assert draft.min_chars == effective.minimum


def test_a_text_at_the_limit_is_accepted(harness: ComposeHarness) -> None:
    projection = harness.technocore.status().projection
    assert projection is not None
    limit = projection.effective_payload_limits["text"].maximum

    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text="a" * limit
    )

    assert draft.swept_chars == limit


def test_a_text_one_past_the_limit_is_refused(harness: ComposeHarness) -> None:
    projection = harness.technocore.status().projection
    assert projection is not None
    limit = projection.effective_payload_limits["text"].maximum

    with pytest.raises(ComposeError) as caught:
        harness.service.draft(
            session_id=harness.session_id, room=TEST_ROOM, text="a" * (limit + 1)
        )

    assert caught.value.reason in {"text_rejected", "text_too_long"}


def test_a_text_that_sweeps_to_nothing_is_refused(harness: ComposeHarness) -> None:
    """Invisible characters only: nothing visible survives the sweep."""
    with pytest.raises(ComposeError) as caught:
        harness.service.draft(
            session_id=harness.session_id, room=TEST_ROOM, text="​​  \t"
        )

    assert caught.value.reason == "text_rejected"


def test_a_tighter_published_limit_is_honoured(engine: Engine) -> None:
    """A live service publishing a smaller bound is respected locally.

    Discovered here rather than as a 400 from the server after the user
    approved a publication.
    """
    from station_api.technocore.client import ReadOnlyTechnocoreClient
    from station_api.technocore.service import TechnocoreService

    from tests.security.technocore_fixtures import build_documents, message_body_schema

    docs = build_documents(parsed=True)
    message_body_schema(docs["openapi"])["properties"]["text"]["maxLength"] = 32
    payloads = build_documents()
    payloads["/openapi.json"] = docs["openapi"]

    def respond(request: httpx.Request) -> httpx.Response:
        body = payloads.get(request.url.path)
        if body is None:
            return httpx.Response(404, text="not found")
        if isinstance(body, dict):
            return httpx.Response(200, json=body)
        return httpx.Response(200, text=body, headers={"Content-Type": "text/plain"})

    live = TechnocoreService(
        engine=engine,
        client=ReadOnlyTechnocoreClient(
            transport=httpx.MockTransport(respond), sleep=lambda _: None
        ),
    )
    live.refresh()
    assert live.manifest_current is True

    harness = build_harness(engine, technocore=live)
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text="a" * 32
    )
    assert draft.max_chars == 32

    with pytest.raises(ComposeError) as caught:
        harness.service.draft(
            session_id=harness.session_id, room=TEST_ROOM, text="a" * 33
        )
    assert caught.value.reason == "text_too_long"


# ---------------------------------------------------------------------------
# Target policy
# ---------------------------------------------------------------------------


def test_the_lobby_is_refused_as_a_composer_target(harness: ComposeHarness) -> None:
    """INV-05 and ADR-0002 4.1, through the service the user reaches."""
    with pytest.raises(ComposeError) as caught:
        harness.service.draft(
            session_id=harness.session_id, room="lobby", text=TEXT
        )

    assert caught.value.reason == "room_refused"
    assert harness.signer.signed == []
    assert harness.writes.send_count == 0


def test_a_room_carrying_a_class_is_reported_to_the_user(
    harness: ComposeHarness,
) -> None:
    """An ephemeral room means the evidence may not survive. Say so."""
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM_ALT, text=TEXT
    )

    assert draft.room_classes == ("e",)
    assert any("gecici" in note for note in draft.target_notes)


# ---------------------------------------------------------------------------
# The three outcomes, through the service
# ---------------------------------------------------------------------------


def test_a_refusal_is_reported_as_a_refusal(engine: Engine) -> None:
    harness = build_harness(engine, handler=answering(422))
    _, signed = _approve(harness)

    result = harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )

    assert result.outcome is WriteOutcome.REFUSED
    assert result.reconciliation_required is False
    state, outcome = _state_of_last_nonce(harness)
    assert state == NonceState.SPENT.value
    assert outcome == WriteOutcomeValue.REFUSED.value


def test_a_lost_response_is_outcome_unknown_and_says_so(engine: Engine) -> None:
    """The case the pinned manual names, carried all the way to the user.

    "Sent" and "failed" are both claims the evidence does not support, so
    the sentence says the nonce is spent and a retry needs a fresh approval.
    """
    harness = build_harness(engine, handler=raising(httpx.ReadTimeout("lost")))
    _, signed = _approve(harness)

    result = harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )

    assert result.outcome is WriteOutcome.OUTCOME_UNKNOWN
    assert result.reconciliation_required is True
    assert "bilinmiyor" in result.detail
    assert "yeni bir onay" in result.detail

    state, outcome = _state_of_last_nonce(harness)
    assert state == NonceState.SPENT.value
    assert outcome == WriteOutcomeValue.OUTCOME_UNKNOWN.value


def test_a_network_exception_is_outcome_unknown_not_an_error(
    engine: Engine,
) -> None:
    harness = build_harness(engine, handler=raising(httpx.ConnectError("no route")))
    _, signed = _approve(harness)

    result = harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )

    assert result.outcome is WriteOutcome.OUTCOME_UNKNOWN


def test_an_accepted_write_whose_receipt_cannot_be_read_is_still_accepted(
    engine: Engine,
) -> None:
    """Accepted-but-readback-failed.

    The server answered 2xx, which is the only evidence available at this
    point, and the receipt being unparseable does not retract it. Package E
    is what turns acceptance into evidence by reading the room back; this
    release does not claim to have done that, and the excerpt is kept as-is.
    """
    harness = build_harness(engine, handler=answering(200, body="<<<not json>>>"))
    _, signed = _approve(harness)

    result = harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )

    assert result.outcome is WriteOutcome.ACCEPTED
    assert result.reconciliation_required is False
    assert "not json" in result.response_excerpt


def test_no_outcome_is_retried_automatically(engine: Engine) -> None:
    """ADR-0002 3. One approval, one attempt, whatever came back."""
    for status in (500, 503, 429):
        harness = build_harness(engine, handler=answering(status))
        _, signed = _approve(harness, room=f"e-test-only-{status}")
        harness.service.send(
            session_id=harness.session_id, send_token=signed.send_token
        )
        assert harness.writes.send_count == 1


def test_a_spent_nonce_is_never_offered_again(engine: Engine) -> None:
    """Every outcome burns it, and the next reservation goes past it."""
    harness = build_harness(engine, handler=raising(httpx.ReadTimeout("lost")))
    _, signed = _approve(harness)
    harness.service.send(session_id=harness.session_id, send_token=signed.send_token)

    spent = int(signed.nonce)
    _, again = _approve(harness)

    assert int(again.nonce) > spent


# ---------------------------------------------------------------------------
# The signer boundary
# ---------------------------------------------------------------------------


def test_the_signer_only_ever_receives_a_canonical_payload(
    harness: ComposeHarness,
) -> None:
    """Raw text cannot be signed, because raw text cannot be a payload.

    A structural property of ``sign_payload``, restated here at the call
    site the composer actually uses (IMP-211).
    """
    _approve(harness)

    assert len(harness.signer.signed) == 1
    payload = harness.signer.signed[0]
    assert payload.swept_text == TEXT
    assert payload.canonical.startswith(f"{TEST_ROOM}|")


def test_nothing_in_the_composer_result_carries_key_material(
    harness: ComposeHarness,
) -> None:
    """The seed never leaves the signer, so it never reaches a result."""
    from tests.security.compose_fixtures import TEST_ONLY_SEED

    draft, signed = _approve(harness)
    result = harness.service.send(
        session_id=harness.session_id, send_token=signed.send_token
    )

    blob = " ".join(
        [
            str(draft),
            str(signed),
            str(result),
        ]
    ).lower()
    assert TEST_ONLY_SEED.hex() not in blob
    for forbidden in ("seed", "private_key", "mnemonic", "passphrase"):
        assert forbidden not in blob


def test_the_nonce_is_reserved_before_the_signature_exists(
    harness: ComposeHarness,
) -> None:
    """Ordering, not preference: the nonce is inside the signed bytes.

    Asserted by reading the payload the signer received - it already carries
    the reserved nonce, so the reservation cannot have happened afterwards.
    """
    _, signed = _approve(harness)

    payload = harness.signer.signed[0]
    assert payload.nonce == signed.nonce
    assert f"|{signed.nonce}|" in payload.canonical
    assert harness.reserver.last_value(did=TEST_ONLY_DID, room=TEST_ROOM) == int(
        signed.nonce
    )


def test_a_failed_signature_does_not_leave_a_dangling_reservation(
    engine: Engine,
) -> None:
    """A number handed out and not used is recorded as cancelled, not lost."""

    class _Exploding:
        def sign(self, payload, *, identity_id, passphrase):  # type: ignore[no-untyped-def]
            raise RuntimeError("TEST ONLY - signer failed")

    harness = build_harness(engine)
    harness.service._signer = _Exploding()

    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=TEXT
    )
    with pytest.raises(RuntimeError):
        harness.service.sign(
            session_id=harness.session_id,
            draft_id=draft.draft_id,
            confirmed_digest=draft.draft_digest,
            vault_passphrase=None,
        )

    state, outcome = _state_of_last_nonce(harness)
    assert state == NonceState.CANCELLED.value
    assert outcome == WriteOutcomeValue.NOT_SENT.value


# ---------------------------------------------------------------------------
# Nonce races through the composer
# ---------------------------------------------------------------------------


def test_concurrent_signatures_never_share_a_nonce(engine: Engine) -> None:
    """Eight approvals prepared at once, in one room.

    Each one is a separate canonical string, so each needs its own number.
    Sharing one would mean the second write is refused as a replay - after
    the user approved it.
    """
    import threading

    harness = build_harness(engine)
    drafts = [
        harness.service.draft(
            session_id=harness.session_id, room=TEST_ROOM, text=f"{TEXT} {index}"
        )
        for index in range(8)
    ]
    nonces: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(len(drafts))

    def sign(index: int) -> None:
        barrier.wait()
        signed = harness.service.sign(
            session_id=harness.session_id,
            draft_id=drafts[index].draft_id,
            confirmed_digest=drafts[index].draft_digest,
            vault_passphrase=None,
        )
        with lock:
            nonces.append(signed.nonce)

    threads = [threading.Thread(target=sign, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()

    assert len(nonces) == 8
    assert len(set(nonces)) == 8


def test_a_second_approval_for_the_same_text_uses_a_new_nonce(
    harness: ComposeHarness,
) -> None:
    """Identical content is still a different write.

    Same canonical text, different nonce, therefore different signed bytes -
    which is what stops a captured signature from being replayed.
    """
    _, first = _approve(harness)
    _, second = _approve(harness)

    assert first.nonce != second.nonce
    assert first.canonical != second.canonical
    assert first.signature != second.signature


def test_the_reservation_survives_a_reopened_engine(engine: Engine) -> None:
    """Crash and resume, through the composer rather than the store alone."""
    harness = build_harness(engine)
    _, signed = _approve(harness)

    resumed = build_harness(engine, reserver=NonceReserver(engine))
    _, after = _approve(resumed)

    assert int(after.nonce) > int(signed.nonce)


def test_time_moves_forward_between_two_sends(harness: ComposeHarness) -> None:
    """A sanity check on the clock floor, without asserting on wall time."""
    _, first = _approve(harness)
    time.sleep(0.002)
    _, second = _approve(harness)

    assert int(second.nonce) > int(first.nonce)
