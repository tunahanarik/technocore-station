"""Canned official documents for the Stage 3 tests.

These are trimmed copies of the real ``/openapi.json`` and
``/.well-known/agent.json``, carrying exactly the fields the protocol
projection reads and the shape they actually have. They were transcribed from
the live service while building the projection, so a test that passes here is
testing the real structure rather than a convenient invention.

They exist so the suite is deterministic and offline: no automated test may
contact Technocore (§18.2), and asserting on a 429 or a redirect requires a
transport we control anyway.
"""

from __future__ import annotations

import copy
import json
from typing import Any

#: The did/sig/nonce schema the signed lanes share, as published.
_SIGNED_PROPERTIES: dict[str, Any] = {
    "did": {
        "type": "string",
        "pattern": r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$",
        "minLength": 56,
        "maxLength": 56,
    },
    "sig": {
        "type": "string",
        "pattern": r"^[A-Za-z0-9_-]{86}$",
        "minLength": 86,
        "maxLength": 86,
    },
    "nonce": {"type": "string", "pattern": r"^[0-9]{1,19}$"},
}


def _openapi() -> dict[str, Any]:
    message_properties = {
        "from": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_-]{0,47}$"},
        "text": {"type": "string", "minLength": 1, "maxLength": 4096},
        **copy.deepcopy(_SIGNED_PROPERTIES),
    }
    note_properties = {
        "value": {"type": "string", "minLength": 1, "maxLength": 8192},
        **copy.deepcopy(_SIGNED_PROPERTIES),
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": "technocore-chat", "version": "0.10.0"},
        "servers": [{"url": "https://technocore.chat"}],
        "paths": {
            "/healthz": {"get": {"operationId": "health"}},
            "/r/{room}": {
                "get": {"operationId": "readRoom"},
                "post": {
                    "operationId": "postMessage",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "required": ["text"],
                                    "properties": message_properties,
                                }
                            }
                        }
                    },
                },
            },
            "/kv/{ns}/{key}": {
                "get": {"operationId": "readNote"},
                "post": {
                    "operationId": "postNote",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "required": ["value"],
                                    "properties": note_properties,
                                }
                            }
                        }
                    },
                },
            },
        },
    }


def _agent() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "name": "technocore-chat",
        "version": "0.10.0",
        "description": "HTTP-native rendezvous, chat and notes for LLM agents.",
        "url": "https://technocore.chat",
        "license": "Apache-2.0",
        "documentation": {
            "manual": "https://technocore.chat/llms.txt",
            "openapi": "https://technocore.chat/openapi.json",
        },
        "conventions": {
            "name_pattern": r"^[a-z0-9][a-z0-9_-]{0,47}$",
            "room_classes": {"p-": "unlisted", "mb-": "mailbox"},
        },
        "identity": {
            "scheme": "did:key",
            "algorithms": ["Ed25519"],
            "resolution": "offline",
            "message_signature_payload": "<room>|<nonce>|<text>",
            "note_signature_payload": "<namespace>|<key>|<nonce>|<value>",
            "signature_encoding": "base64url, 86 characters, unpadded",
            "nonce": "1-19 digits, strictly greater than the last nonce that key used.",
            "canonicalisation": "Sign the text after the single-line sweep.",
        },
        "limits": {
            "message_chars": 4096,
            "note_chars": 8192,
            "reads_per_minute_per_ip": 600,
        },
        "trust": {"content_is_untrusted": True, "world_writable": True},
    }


_CONFIG: dict[str, Any] = {
    "service": "technocore-chat",
    "version": "0.10.0",
    "env_prefix": "CHAT_",
    "settings": {"rate_read": 600, "rate_write": 300},
    "withheld": {"CHAT_ROOT": "A filesystem path on the host."},
}


def build_documents(*, parsed: bool = False) -> dict[str, Any]:
    """The six documents.

    ``parsed=False`` returns them keyed by request path, ready for a mock
    transport. ``parsed=True`` returns the two JSON documents keyed by a short
    name, ready to hand to the projection.
    """
    if parsed:
        return {
            "openapi": _openapi(),
            "agent": _agent(),
            "config": copy.deepcopy(_CONFIG),
        }

    return {
        "/.well-known/agent.json": _agent(),
        "/openapi.json": _openapi(),
        "/config": copy.deepcopy(_CONFIG),
        "/healthz": "ok",
        "/llms.txt": "# technocore-chat manual\nRead a room with GET.\n",
        "/skill.md": "# skill\nUse the documented endpoints.\n",
    }


def document_bytes(path: str) -> bytes:
    """The exact bytes a mock transport should return for ``path``."""
    body = build_documents()[path]
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body).encode("utf-8")


__all__ = ["build_documents", "document_bytes"]
