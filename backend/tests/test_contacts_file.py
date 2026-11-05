"""
tests/test_contacts_file.py — phone validation and CSV checks shared by
campaign upload, lead import and the DNC list (app/core/contacts_file.py).
"""
from __future__ import annotations

import pytest

from app.core.contacts_file import is_valid_phone, normalize_phone, parse_contacts_file
from app.core.exceptions import ValidationError as AppValidationError


@pytest.mark.parametrize("raw, expected", [
    ("9876543210", "+919876543210"),
    ("098765 43210", "+919876543210"),
    ("+91 (98765) 43-210", "+919876543210"),
    ("919876543210", "+919876543210"),
    ("00447911123456", "+447911123456"),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw, ok", [
    ("9876543210", True),
    ("+14155550123", True),
    ("12345", False),
    ("98765432101", False),   # 11 digits
    ("5876543210", False),    # Indian mobiles start 6-9
    ("abcdefghij", False),
])
def test_is_valid_phone(raw, ok):
    assert is_valid_phone(normalize_phone(raw)) is ok


def test_valid_csv_parses():
    rows = parse_contacts_file(b"phone,name\n9876543210,Asha\n+91 91234 56789,Ravi\n", "c.csv")
    assert [r["phone"] for r in rows] == ["+919876543210", "+919123456789"]


def test_rejects_invalid_phone_with_row_number():
    with pytest.raises(AppValidationError) as exc:
        parse_contacts_file(b"phone,name\n9876543210,Asha\n12345,Bad\n", "c.csv")
    assert "row 3 (12345)" in exc.value.message


def test_rejects_inconsistent_column_count():
    with pytest.raises(AppValidationError) as exc:
        parse_contacts_file(b"phone,name,city\n9876543210,Asha,Pune\n9123456789,Ravi\n", "c.csv")
    assert "Line 3 has 2 columns" in exc.value.message


def test_rejects_broken_quotes():
    with pytest.raises(AppValidationError) as exc:
        parse_contacts_file(b'phone,name\n9876543210,"Asha\n9123456789,Ravi\n', "c.csv")
    assert "quotation mark" in exc.value.message


def test_blank_lines_are_ignored():
    rows = parse_contacts_file(b"phone,name\n9876543210,Asha\n\n,\n", "c.csv")
    assert len(rows) == 1
