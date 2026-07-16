from datetime import date, datetime

from app.connectors.drivers.mongodb_driver import _to_cell


class _FakeObjectId:
    def __str__(self):
        return "abc123"


def test_primitives_pass_through_unchanged():
    assert _to_cell(None) is None
    assert _to_cell("hello") == "hello"
    assert _to_cell(42) == 42
    assert _to_cell(3.14) == 3.14
    assert _to_cell(True) is True


def test_datetime_formats_as_clean_iso_string():
    assert _to_cell(datetime(2026, 5, 21, 9, 6, 52, 493000)) == "2026-05-21T09:06:52.493000"


def test_date_formats_as_clean_iso_string():
    assert _to_cell(date(2026, 5, 21)) == "2026-05-21"


def test_list_becomes_none_instead_of_a_repr_blob():
    assert _to_cell([{"type": "note", "createdAt": datetime(2026, 5, 21)}]) is None


def test_dict_becomes_none_instead_of_a_repr_blob():
    assert _to_cell({"a": 1}) is None


def test_other_non_primitive_scalars_still_stringify():
    assert _to_cell(_FakeObjectId()) == "abc123"
