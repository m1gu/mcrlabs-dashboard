from decimal import Decimal

from downloader_qbench_data.ingestion.utils import ensure_int_list, safe_decimal, safe_int


def test_safe_int_with_valid_values():
    assert safe_int(5) == 5
    assert safe_int("10") == 10


def test_safe_int_with_invalid_values(caplog):
    caplog.set_level("WARNING")
    assert safe_int(None) is None
    assert safe_int("not-a-number") is None


def test_ensure_int_list_filters_invalid(caplog):
    caplog.set_level("WARNING")
    assert ensure_int_list([1, "2", "bad", None]) == [1, 2]
    assert ensure_int_list(None) == []


def test_safe_decimal_conversion(caplog):
    caplog.set_level("WARNING")
    assert safe_decimal("6.3") == Decimal("6.3")
    assert safe_decimal(2) == Decimal("2")
    assert safe_decimal(None) is None
    assert safe_decimal("not-a-number") is None

def test_safe_decimal_strips_units(caplog):
    caplog.set_level("WARNING")
    assert safe_decimal("6.34g") == Decimal("6.34")
    assert safe_decimal("10.6oz") == Decimal("10.6")
