"""The provider credential's envelope: the audit shape, and the one inversion.

Package E's audit envelope is the template here, and copying a template is
where a rule gets inherited by accident. So the test that matters most in
this file is the pair at the bottom: the audit chain's material still refuses
to be overwritten, and this envelope **replaces on purpose**, and both are
asserted side by side so nobody has to guess which behaviour was intended
(ADR-0005 7).

The rest is the usual boundary: the credential is not in the file in the
clear, is not in the database at all, is described by a fingerprint, and is
refused outright when it is too short to be redactable - which is the trap
ADR-0005 8 names, because ``register_secret`` ignores a short value in
silence.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session
from station_api.config import Settings
from station_api.evidence.audit_envelope import AuditEnvelope, AuditEnvelopeError
from station_api.logging_setup import (
    _MIN_REGISTERABLE_LENGTH,
    contains_registered_secret,
)
from station_api.opencode import credential_store as credential_store_module
from station_api.opencode.credential_store import (
    CREDENTIAL_ID,
    DOMAIN_SEPARATION_LABEL,
    ENVELOPE_FORMAT,
    ENVELOPE_KIND,
    ENVELOPE_VERSION,
    MIN_KEY_LENGTH,
    ApiKeyEnvelope,
    assert_storable,
    credential_dir,
    credential_path,
    fingerprint,
)
from station_api.opencode.errors import (
    CredentialEnvelopeError,
    OpenCodeConfigurationError,
    OpenCodeError,
)
from station_api.opencode.service import OpenCodeService
from station_api.strict_json import b64u_decode, b64u_encode
from station_api.vault.errors import (
    VaultAclError,
    VaultCapabilityError,
    VaultError,
    VaultUnlockError,
)

from tests.conftest import TEST_ONLY_OPENCODE_CREDENTIAL

pytestmark = pytest.mark.security

IS_WINDOWS = sys.platform == "win32"

windows_only = pytest.mark.skipif(
    not IS_WINDOWS,
    reason="DPAPI is a Windows API; the non-Windows path is asserted separately",
)

SECOND_CREDENTIAL = "TEST-ONLY-second-credential-000000002"


@pytest.fixture
def envelope(data_dir: Path) -> ApiKeyEnvelope:
    return ApiKeyEnvelope(data_dir)


# ---------------------------------------------------------------------------
# What may be stored at all
# ---------------------------------------------------------------------------


def test_a_credential_too_short_to_redact_is_refused() -> None:
    """The trap, closed at the door (ADR-0005 8).

    ``register_secret`` silently ignores anything under sixteen characters.
    A shorter credential would therefore be stored *and never scrubbed from a
    log line*, so the floor here is above that threshold and refuses rather
    than accepting a value we could not keep the redaction promise about.
    """
    assert MIN_KEY_LENGTH > _MIN_REGISTERABLE_LENGTH

    for short in ("", "abc", "x" * (MIN_KEY_LENGTH - 1)):
        with pytest.raises(CredentialEnvelopeError):
            assert_storable(short)


def test_a_credential_with_surrounding_whitespace_is_refused() -> None:
    """Trimming silently would store a value the user cannot see they typed."""
    with pytest.raises(CredentialEnvelopeError):
        assert_storable(f" {TEST_ONLY_OPENCODE_CREDENTIAL} ")


def test_storing_does_not_validate_the_shape_of_a_credential() -> None:
    """A format check that passed would look like a verification.

    Nothing about this build can verify a key (ADR-0005 4), so accepting an
    arbitrary long string is the honest behaviour: the only refusals are
    about what we could hold safely, never about what looks plausible.
    """
    assert_storable("x" * MIN_KEY_LENGTH)
    assert_storable("this-is-not-shaped-like-any-provider-key-at-all")


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


@windows_only
def test_the_envelope_has_the_audit_shape_and_hides_the_credential(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)

    path = credential_path(data_dir)
    assert path.is_file()
    raw = path.read_bytes()

    document = json.loads(raw)
    assert set(document) == {"format", "version", "kind", "created_at", "dpapi_blob"}
    assert document["format"] == ENVELOPE_FORMAT
    assert document["version"] == ENVELOPE_VERSION
    assert document["kind"] == ENVELOPE_KIND

    assert TEST_ONLY_OPENCODE_CREDENTIAL.encode() not in raw
    assert envelope.load() == TEST_ONLY_OPENCODE_CREDENTIAL


@windows_only
def test_the_envelope_is_versioned_and_kind_checked(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    """Each mutation starts from a **fresh** envelope. It did not before.

    The previous loop called ``path.read_bytes()`` *inside* the loop, so
    round two mutated round one's already-broken file. ``version=99`` stuck,
    every later round was refused on the version, and the ``kind`` and
    ``format`` branches were never reached: deleting either check from
    ``_unwrap`` left the whole suite green. Reading the good bytes once,
    before the loop, and restoring them after each round is the entire fix -
    and the restore doubles as proof that the file was broken by *this*
    mutation and not by the previous one.
    """
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    path = credential_path(data_dir)
    good = path.read_bytes()
    assert envelope.load() == TEST_ONLY_OPENCODE_CREDENTIAL

    for mutation in ({"version": 99}, {"kind": "material"}, {"format": "other"}):
        document = json.loads(good)
        document.update(mutation)
        path.write_bytes(json.dumps(document).encode())
        with pytest.raises(CredentialEnvelopeError):
            envelope.load()

        path.write_bytes(good)
        assert envelope.load() == TEST_ONLY_OPENCODE_CREDENTIAL, (
            f"the envelope did not survive round-tripping past {mutation}"
        )


@windows_only
def test_an_envelope_with_a_missing_or_extra_or_mistyped_field_is_refused(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    """The other half of SI-239, which nothing held.

    ``require_exact_keys`` and the ``created_at`` type check were both
    unreachable from any test: removing either one changed no result. Both
    are load-bearing - an envelope missing ``dpapi_blob`` or carrying a sixth
    field is not one this build wrote, and a build that read it anyway would
    be guessing about a file that holds a credential.
    """
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    path = credential_path(data_dir)
    good = path.read_bytes()
    fields = ("format", "version", "kind", "created_at", "dpapi_blob")

    def refuses(document: dict[str, Any], why: str) -> None:
        path.write_bytes(json.dumps(document).encode())
        with pytest.raises(CredentialEnvelopeError):
            envelope.load()
        path.write_bytes(good)
        assert envelope.load() == TEST_ONLY_OPENCODE_CREDENTIAL, why

    for missing in fields:
        document = json.loads(good)
        del document[missing]
        refuses(document, f"a envelope without {missing!r} was accepted")

    document = json.loads(good)
    document["extra"] = "a field this build never wrote"
    refuses(document, "an envelope with a sixth field was accepted")

    document = json.loads(good)
    document["created_at"] = 0
    refuses(document, "an envelope with a non-string created_at was accepted")


@windows_only
def test_an_audit_material_envelope_cannot_be_read_as_a_credential(
    data_dir: Path,
) -> None:
    """Domain separation, in-band, because DPAPI's entropy is one constant.

    ``dpapi.protect`` takes no entropy parameter, so an audit blob and a
    credential blob unprotect for the same user equally well. Reading one as
    the other would put thirty-two bytes of MAC material into an outbound
    credential header, which is why the plaintext carries a label and the
    label is required on load.
    """
    audit = AuditEnvelope(data_dir)
    audit.create_material()

    target = credential_path(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)

    # The audit envelope's own bytes, moved into this file's position, with
    # the outer fields corrected so only the inner label can refuse it.
    document = json.loads(audit.material_file.read_bytes())
    document["format"] = ENVELOPE_FORMAT
    document["kind"] = ENVELOPE_KIND
    target.write_bytes(json.dumps(document).encode())

    with pytest.raises(CredentialEnvelopeError):
        ApiKeyEnvelope(data_dir).load()


def test_the_domain_label_is_a_fixed_public_constant() -> None:
    """It separates domains; it is not a secret and does not pretend to be."""
    assert DOMAIN_SEPARATION_LABEL.startswith(b"technocore-station/opencode/")
    assert DOMAIN_SEPARATION_LABEL.endswith(b"\x00")


@windows_only
def test_a_malformed_envelope_is_a_refusal_and_not_a_crash(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    credential_path(data_dir).parent.mkdir(parents=True, exist_ok=True)
    credential_path(data_dir).write_bytes(b"{not json")

    with pytest.raises(CredentialEnvelopeError):
        envelope.load()


def test_loading_when_nothing_is_stored_is_a_refusal(envelope: ApiKeyEnvelope) -> None:
    assert envelope.exists() is False
    with pytest.raises(CredentialEnvelopeError):
        envelope.load()


# ---------------------------------------------------------------------------
# The one deliberate inversion, asserted beside the rule it inverts
# ---------------------------------------------------------------------------


@windows_only
def test_a_credential_is_replaceable_because_a_user_must_be_able_to_rotate_one(
    envelope: ApiKeyEnvelope,
) -> None:
    first = envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    second = envelope.store(SECOND_CREDENTIAL)

    assert envelope.load() == SECOND_CREDENTIAL
    assert first != second


@windows_only
def test_the_audit_material_still_refuses_to_be_overwritten(data_dir: Path) -> None:
    """The half of the pair that must not change.

    Copying the audit envelope's shape is right; copying its never-overwrite
    rule would have been wrong, and copying this test's absence would have
    left a future reader unable to tell which was intended. Both behaviours
    are pinned, in one file, next to each other.
    """
    audit = AuditEnvelope(data_dir)
    audit.create_material()

    with pytest.raises(AuditEnvelopeError):
        audit.create_material()


# ---------------------------------------------------------------------------
# The fingerprint, and what reaches the database
# ---------------------------------------------------------------------------


def test_the_fingerprint_names_a_credential_without_revealing_it() -> None:
    value = fingerprint(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert len(value) == 64
    assert TEST_ONLY_OPENCODE_CREDENTIAL not in value
    assert fingerprint(TEST_ONLY_OPENCODE_CREDENTIAL) == value
    assert fingerprint(SECOND_CREDENTIAL) != value


@windows_only
def test_only_a_relative_path_a_time_and_a_fingerprint_reach_the_database(
    engine: Engine, settings: Settings, data_dir: Path
) -> None:
    service = OpenCodeService(engine=engine, data_dir=settings.data_dir)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)

    columns = {
        column["name"] for column in inspect(engine).get_columns(
            "opencode_credential_metadata"
        )
    }
    assert columns == {
        "id",
        "envelope_relpath",
        "fingerprint",
        "created_at",
        "updated_at",
    }

    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT id, envelope_relpath, fingerprint FROM opencode_credential_metadata"
        ).fetchone()

    assert row is not None
    assert row[0] == CREDENTIAL_ID
    # Relative, never absolute (SI-36): no drive letter, no data directory.
    assert not row[1].startswith("/")
    assert ":" not in row[1]
    assert str(data_dir) not in row[1]
    assert row[2] == fingerprint(TEST_ONLY_OPENCODE_CREDENTIAL)


@windows_only
def test_forgetting_a_credential_removes_the_file_and_the_row(
    engine: Engine, settings: Settings
) -> None:
    service = OpenCodeService(engine=engine, data_dir=settings.data_dir)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)
    assert ApiKeyEnvelope(settings.data_dir).exists()

    view = service.forget_credential()

    assert view.configured is False
    assert view.fingerprint_short == ""
    assert not ApiKeyEnvelope(settings.data_dir).exists()
    with engine.connect() as connection:
        count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM opencode_credential_metadata"
        ).scalar()
    assert count == 0


@windows_only
def test_the_acl_is_restricted_to_the_current_user_and_system(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    """Read the DACL back, exactly as the vault's own test does."""
    from station_api.vault.windows_acl import acl_grantee_sids, current_user_sid

    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)

    granted = sorted(acl_grantee_sids(credential_path(data_dir)))
    assert granted == sorted(("S-1-5-18", current_user_sid()))


# ---------------------------------------------------------------------------
# The store path's redaction window
# ---------------------------------------------------------------------------
#
# ``OpenCodeService.store_credential`` wraps the envelope write in
# ``_registered``, which puts the key in the redaction registry for the
# duration of the call. Until now nothing drove that: a mutation review
# deleted the registration and only the baseline failures moved, because
# every test that asserted redaction went through the *client* path, which
# registers the key separately.
#
# The window is what makes an exception raised inside the write safe. DPAPI,
# an ACL call and a rename all happen in there, and any of them can raise
# with the value on the stack.


def test_the_store_path_registers_the_key_for_redaction_while_it_writes(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observed from inside the envelope write, which is where it matters.

    The probe replaces :meth:`ApiKeyEnvelope.store` so no DPAPI call is made
    and no envelope is left behind - the assertion is about the registry, not
    about the file - and asks the redaction registry the one question that
    can distinguish a live control from a comment: *is the key registered
    right now?*
    """
    from station_api.logging_setup import contains_registered_secret

    observed: list[bool] = []

    def probe(self: ApiKeyEnvelope, key: str) -> str:
        observed.append(contains_registered_secret(key))
        return fingerprint(key)

    monkeypatch.setattr(ApiKeyEnvelope, "store", probe)

    service = OpenCodeService(engine=engine, data_dir=settings.data_dir)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert observed == [True], "the key was not registered while it was being written"


def test_the_store_path_drops_the_key_from_the_registry_when_it_returns(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registered for exactly as long as it is in use, and no longer.

    A registry that only grows is a registry that eventually scrubs ordinary
    log lines, which is how a redaction control gets switched off in
    practice. The client path already asserts this; the store path did not.
    """
    from station_api.logging_setup import contains_registered_secret

    monkeypatch.setattr(ApiKeyEnvelope, "store", lambda self, key: fingerprint(key))

    service = OpenCodeService(engine=engine, data_dir=settings.data_dir)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert not contains_registered_secret(TEST_ONLY_OPENCODE_CREDENTIAL)


def test_the_key_is_still_registered_when_the_envelope_write_raises(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case the window exists for, and the cleanup that must still run.

    A failure inside the write is exactly when a traceback carrying the value
    would be logged, so the registration has to be live at the moment the
    exception is raised - and gone again once it has propagated.
    """
    from station_api.logging_setup import contains_registered_secret

    observed: list[bool] = []

    def explode(self: ApiKeyEnvelope, key: str) -> str:
        observed.append(contains_registered_secret(key))
        raise OSError("simulated DPAPI failure")

    monkeypatch.setattr(ApiKeyEnvelope, "store", explode)

    service = OpenCodeService(engine=engine, data_dir=settings.data_dir)
    with pytest.raises(OSError):
        service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert observed == [True]
    assert not contains_registered_secret(TEST_ONLY_OPENCODE_CREDENTIAL)


# ---------------------------------------------------------------------------
# The file and the row must not be able to disagree
# ---------------------------------------------------------------------------
#
# The fingerprint is the only handle a user has on "which key is stored"
# (SI-242). ``store_credential`` writes two things with no transaction
# between them, and the order used to be file first, so a database failure
# after a successful write left the row naming the *previous* key while the
# envelope held the new one - and the status endpoint reported that stale
# fingerprint as configured. The two tests below are the two ways the probe
# produced that state.


@windows_only
def test_a_failed_metadata_write_never_leaves_a_fingerprint_naming_another_key(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database failure must cost the claim, never make it wrong.

    ``_withdraw_credential_row`` deletes with ``session.execute`` and the
    insert uses ``session.add``, so breaking ``add`` alone reproduces exactly
    the failure the probe injected: the envelope on disk is the new key and
    the row could not be written. The connection must read as *not
    configured* - never as configured under the old fingerprint (SI-263).
    """
    service = OpenCodeService(engine=engine, data_dir=settings.data_dir)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)

    before = service.describe()
    assert before.configured is True
    assert before.fingerprint_short == fingerprint(TEST_ONLY_OPENCODE_CREDENTIAL)[:12]

    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(Session, "add", refuse)
    with pytest.raises(RuntimeError):
        service.store_credential(SECOND_CREDENTIAL)
    monkeypatch.undo()

    after = service.describe()
    assert after.configured is False
    assert after.fingerprint_short == ""
    assert after.fingerprint_short != before.fingerprint_short, (
        "the status document named a key that is no longer the stored one"
    )
    # And the reason the old fingerprint would have been a lie: the key on
    # disk really is the new one.
    assert ApiKeyEnvelope(settings.data_dir).load() == SECOND_CREDENTIAL


@windows_only
def test_a_failure_after_the_rename_leaves_no_envelope_at_all(
    envelope: ApiKeyEnvelope, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed on the far side of ``os.replace``.

    The old ``except BaseException`` only removed the temporary file, which
    is nothing to do once the rename has happened: the probe showed a caller
    seeing a failure while the previous key was gone and an unrestricted new
    one was live. The only honest outcome there is *no envelope*, which
    ``describe()`` reports as not configured and a user can act on.
    """
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    target = credential_path(data_dir)
    real = credential_store_module.windows_acl.restrict_to_current_user

    def fail_after_replace(path: Path) -> str:
        if path == target:
            raise VaultAclError("simulated failure after os.replace")
        return real(path)

    monkeypatch.setattr(
        credential_store_module.windows_acl,
        "restrict_to_current_user",
        fail_after_replace,
    )
    with pytest.raises(OpenCodeConfigurationError):
        envelope.store(SECOND_CREDENTIAL)
    monkeypatch.undo()

    assert not envelope.exists()
    assert list(credential_dir(data_dir).glob("*.tmp")) == []
    with pytest.raises(CredentialEnvelopeError):
        envelope.load()


# ---------------------------------------------------------------------------
# Every failure stays inside the OpenCode hierarchy
# ---------------------------------------------------------------------------
#
# ``station_api.opencode.errors`` says every failure here is fail-closed in
# the connection's own vocabulary. The two most likely real faults - DPAPI
# unavailable and an ACL that could not be applied - were raised by the vault
# as ``VaultError`` subclasses, which no route catches. The shield turned
# them into an opaque 500 carrying no key, so nothing leaked; the contract
# was still false and the user was told nothing.


@windows_only
def test_a_dpapi_capability_failure_is_named_in_the_opencode_hierarchy(
    envelope: ApiKeyEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(payload: bytes) -> bytes:
        raise VaultCapabilityError("simulated DPAPI capability failure")

    monkeypatch.setattr(credential_store_module.dpapi, "protect", unavailable)

    with pytest.raises(OpenCodeConfigurationError) as caught:
        envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert isinstance(caught.value, OpenCodeError)
    assert not isinstance(caught.value, VaultError)
    assert isinstance(caught.value.__cause__, VaultCapabilityError)
    assert "DPAPI" in str(caught.value)
    assert TEST_ONLY_OPENCODE_CREDENTIAL not in str(caught.value)


@windows_only
def test_an_acl_failure_is_named_in_the_opencode_hierarchy(
    envelope: ApiKeyEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(path: Path) -> str:
        raise VaultAclError("simulated ACL failure")

    monkeypatch.setattr(
        credential_store_module.windows_acl, "restrict_to_current_user", refuse
    )

    with pytest.raises(OpenCodeConfigurationError) as caught:
        envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert isinstance(caught.value, OpenCodeError)
    assert not isinstance(caught.value, VaultError)
    assert isinstance(caught.value.__cause__, VaultAclError)
    monkeypatch.undo()
    assert not envelope.exists()


@windows_only
def test_a_blob_dpapi_cannot_unprotect_is_a_credential_refusal_not_a_vault_error(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    """The read-side twin: a tampered blob used to escape as VaultUnlockError."""
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    path = credential_path(data_dir)

    document = json.loads(path.read_bytes())
    blob = bytearray(b64u_decode(document["dpapi_blob"]))
    blob[-1] ^= 0xFF
    document["dpapi_blob"] = b64u_encode(bytes(blob))
    path.write_bytes(json.dumps(document).encode())

    with pytest.raises(CredentialEnvelopeError) as caught:
        envelope.load()

    assert isinstance(caught.value, OpenCodeError)
    assert not isinstance(caught.value, VaultError)
    assert isinstance(caught.value.__cause__, VaultUnlockError)


# ---------------------------------------------------------------------------
# Two writers and two readers of one file
# ---------------------------------------------------------------------------


@windows_only
def test_concurrent_readers_and_writers_never_raise_a_raw_os_error(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    """Windows refuses ``os.replace`` while a reader holds the target open.

    Unsynchronised, the probe saw 53 failures across 160 operations, 13 of
    them ``PermissionError`` - an ``OSError``, outside this package's
    hierarchy, so an HTTP 500. The write was already fail-safe (the previous
    key survived, and no temporary file was left), so this is about the error
    *type* and about ``load()`` having no production caller yet: package H's
    executor would have met it first, in the field.
    """
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    known = {TEST_ONLY_OPENCODE_CREDENTIAL, SECOND_CREDENTIAL}

    errors: list[BaseException] = []
    seen: list[str] = []
    lock = threading.Lock()

    def write(value: str) -> None:
        for _ in range(15):
            try:
                envelope.store(value)
            except BaseException as exc:
                with lock:
                    errors.append(exc)

    def read() -> None:
        for _ in range(30):
            try:
                value = envelope.load()
            except BaseException as exc:
                with lock:
                    errors.append(exc)
            else:
                with lock:
                    seen.append(value)

    threads = [
        threading.Thread(target=write, args=(TEST_ONLY_OPENCODE_CREDENTIAL,)),
        threading.Thread(target=write, args=(SECOND_CREDENTIAL,)),
        threading.Thread(target=read),
        threading.Thread(target=read),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [], f"concurrent access raised {len(errors)} times"
    assert set(seen) <= known
    assert envelope.load() in known
    assert list(credential_dir(data_dir).glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# The ACL lands before the bytes, and covers the directory
# ---------------------------------------------------------------------------


@windows_only
def test_the_envelope_is_restricted_before_a_single_byte_is_written(
    envelope: ApiKeyEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The docstring's claim, measured rather than believed.

    Under ``mkstemp`` the order was write, fsync, ACL, and a trace showed 537
    bytes already on disk under an inherited DACL when the ACL call ran. The
    file is now created empty with ``O_CREAT | O_EXCL`` and restricted at
    zero bytes, so the first ACL call on a file must see an empty one.
    """
    real = credential_store_module.windows_acl.restrict_to_current_user
    sizes: list[int] = []

    def watched(path: Path) -> str:
        if path.is_file():
            sizes.append(path.stat().st_size)
        return real(path)

    monkeypatch.setattr(
        credential_store_module.windows_acl, "restrict_to_current_user", watched
    )
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert sizes, "no ACL call was made on a file at all"
    assert sizes[0] == 0, (
        f"{sizes[0]} bytes of envelope existed before the ACL was applied"
    )


@windows_only
def test_the_credential_directory_is_restricted_too(
    envelope: ApiKeyEnvelope, data_dir: Path
) -> None:
    """The file's protected DACL is what matters; the directory is completeness.

    Windows lets an Administrator take ownership regardless, so this is not a
    trust boundary - it is the gap that had no reason to exist. The vault's
    equivalent gap is recorded as an accepted limitation (SI-266) rather than
    quietly shared.
    """
    from station_api.vault.windows_acl import acl_grantee_sids, current_user_sid

    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)

    granted = sorted(acl_grantee_sids(credential_dir(data_dir)))
    assert granted == sorted(("S-1-5-18", current_user_sid()))


# ---------------------------------------------------------------------------
# Registration belongs to the accessor, not to a docstring
# ---------------------------------------------------------------------------
#
# ``load()`` used to promise that ``OpenCodeService`` registered the key for
# redaction "around every use". The service never called ``load()`` at all,
# so the sentence described a caller that did not exist - and package H's
# executor, reading it, would have had no reason to register anything.


@windows_only
def test_load_on_its_own_registers_nothing(envelope: ApiKeyEnvelope) -> None:
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    key = envelope.load()
    assert not contains_registered_secret(key), (
        "load() registered the key, so its docstring's warning is stale"
    )


@windows_only
def test_opened_registers_the_key_for_the_block_and_forgets_it_after(
    envelope: ApiKeyEnvelope,
) -> None:
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)

    with envelope.opened() as key:
        assert key == TEST_ONLY_OPENCODE_CREDENTIAL
        assert contains_registered_secret(key)

    assert not contains_registered_secret(TEST_ONLY_OPENCODE_CREDENTIAL)


@windows_only
def test_opened_forgets_the_key_even_when_the_block_raises(
    envelope: ApiKeyEnvelope,
) -> None:
    """The case the contextmanager exists for.

    A caller that raised mid-use is exactly the caller that would have
    skipped a hand-written ``forget_secret``, leaving a registry that only
    grows - which is how a redaction control gets switched off in practice.
    """
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    observed: list[bool] = []

    with pytest.raises(RuntimeError), envelope.opened() as key:
        observed.append(contains_registered_secret(key))
        raise RuntimeError("the caller failed mid-use")

    assert observed == [True]
    assert not contains_registered_secret(TEST_ONLY_OPENCODE_CREDENTIAL)


@windows_only
def test_a_row_without_an_envelope_names_no_key_at_all(
    engine: Engine, settings: Settings
) -> None:
    """"Not configured" must not come with a fingerprint beside it.

    ``configured`` was already gated on the file existing, but the
    fingerprint, and both timestamps, came from the row alone - so an
    envelope removed from underneath the row produced a status document that
    said *not configured* and still named a key. That is the same wrong
    answer as SI-263's, in a quieter voice: a user reading it would believe
    the key survives somewhere.
    """
    service = OpenCodeService(engine=engine, data_dir=settings.data_dir)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)
    assert service.describe().fingerprint_short != ""

    credential_path(settings.data_dir).unlink()

    view = service.describe()
    assert view.configured is False
    assert view.fingerprint_short == ""
    assert view.configured_at is None
    assert view.updated_at is None
