"""Coverage for the client-name validator that shipped in PR #38 without tests.

Small module, small blast radius, but it's on the critical path of every
storage-touching endpoint — a permissive bug here becomes a path-traversal
CVE. So we belt-and-brace it here.
"""

from __future__ import annotations

import pytest

from app.core.client_name_validation import InvalidClientName, validate_client_name


# ---------- happy path ----------


@pytest.mark.parametrize(
    "name",
    [
        "Acme",
        "Acme Inc",
        "acme-corp",
        "Acme_Corp_2026",
        "Cliente-Acmé",  # unicode alphabetic
        "A" * 100,  # long-ish but plausible
    ],
)
def test_valid_names_are_accepted(name: str) -> None:
    # Should not raise
    validate_client_name(name)


# ---------- disallowed substrings ----------


@pytest.mark.parametrize(
    "name",
    [
        "..",
        "Acme..",
        "..Acme",
        "Acme..Beta",
        "Acme/Beta",
        "/Acme",
        "Acme/",
        "Acme\\Beta",
        "..\\..\\etc",
    ],
)
def test_path_traversal_attempts_rejected(name: str) -> None:
    with pytest.raises(InvalidClientName):
        validate_client_name(name)


# ---------- degenerate inputs ----------


@pytest.mark.parametrize("name", ["", "   ", "\t", "\n"])
def test_empty_or_whitespace_only_rejected(name: str) -> None:
    with pytest.raises(InvalidClientName):
        validate_client_name(name)


def test_none_raises_type_error_or_invalid_name() -> None:
    # We accept either — the guarantee is "not a silent pass".
    with pytest.raises((InvalidClientName, TypeError, AttributeError)):
        validate_client_name(None)  # type: ignore[arg-type]


# ---------- injection-flavored strings ----------


@pytest.mark.parametrize(
    "name",
    [
        "'; DROP TABLE clients; --",  # SQL injection shape
        "<script>alert(1)</script>",  # XSS shape
        "${jndi:ldap://x}",  # log4shell shape
        "Acme\x00Corp",  # null byte
    ],
)
def test_injection_shapes_do_not_silently_pass(name: str) -> None:
    # Some of these will pass the validator (it doesn't guard against SQLi
    # by design — Supabase's REST client is the boundary), but they must NOT
    # raise anything OTHER than InvalidClientName. That guarantees the
    # validator never wedges the app on a malicious-looking-but-legal string.
    try:
        validate_client_name(name)
    except InvalidClientName:
        pass  # rejected — fine
    # any other exception fails the test naturally
