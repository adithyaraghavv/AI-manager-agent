from datetime import datetime, timezone

import pytest

from app.core.file_naming import build_filename


def test_basic_filename_format():
    ts = datetime(2026, 7, 29, 10, 30, 0, tzinfo=timezone.utc)
    name = build_filename("Pricing", "Hillenbrand", "xlsx", timestamp=ts)
    assert name == "Marlabs_Pricing_Hillenbrand_20260729T103000Z.xlsx"


def test_sanitizes_unsafe_characters():
    ts = datetime(2026, 7, 29, tzinfo=timezone.utc)
    name = build_filename("Approved HLD", "Acme & Co.", "docx", timestamp=ts)
    assert name.startswith("Marlabs_Approved_HLD_Acme_Co_")
    assert name.endswith(".docx")


def test_extension_leading_dot_stripped():
    ts = datetime(2026, 7, 29, tzinfo=timezone.utc)
    name = build_filename("SOW", "Client1", ".pdf", timestamp=ts)
    assert name.endswith(".pdf")
    assert ".pdf." not in name


def test_empty_doc_type_raises():
    with pytest.raises(ValueError):
        build_filename("###", "Client1", "pdf")
