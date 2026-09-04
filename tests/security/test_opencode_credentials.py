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
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect
from station_api.config import Settings
from station_api.evidence.audit_envelope import AuditEnvelope, AuditEnvelopeError
from station_api.logging_setup import _MIN_REGISTERABLE_LENGTH
from station_api.opencode.credentials import (
    CREDENTIAL_ID,
    DOMAIN_SEPARATION_LABEL,
    ENVELOPE_FORMAT,
    ENVELOPE_KIND,
    ENVELOPE_VERSION,
    MIN_KEY_LENGTH,
    ApiKeyEnvelope,
    assert_storable,
    credential_path,
    fingerprint,
)
from station_api.opencode.errors import CredentialEnvelopeError
from station_api.opencode.service import OpenCodeService

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
    envelope.store(TEST_ONLY_OPENCODE_CREDENTIAL)
    path = credential_path(data_dir)

    for mutation in ({"version": 99}, {"kind": "material"}, {"format": "other"}):
        document = json.loads(path.read_bytes())
        document.update(mutation)
        path.write_bytes(json.dumps(document).encode())
        with pytest.raises(CredentialEnvelopeError):
            envelope.load()


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
