from datetime import datetime, timezone

from downloader_qbench_data.ingestion.utils import parse_qbench_datetime


def test_parse_datetime_formats():
    assert parse_qbench_datetime("02/14/2025 06:57 PM") == datetime(2025, 2, 14, 18, 57)
    assert parse_qbench_datetime("02/14/2025") == datetime(2025, 2, 14)
    assert parse_qbench_datetime("2025-02-14T18:57:00+0000") == datetime(2025, 2, 14, 18, 57, tzinfo=timezone.utc)
    assert parse_qbench_datetime("1745606180") == datetime.fromtimestamp(1745606180)


def test_parse_datetime_invalid_returns_none(caplog):
    caplog.set_level("WARNING")
    assert parse_qbench_datetime("not-a-date") is None
