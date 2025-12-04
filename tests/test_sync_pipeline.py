from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from downloader_qbench_data.ingestion.utils import SkippedEntity

from downloader_qbench_data.ingestion import pipeline


@pytest.fixture
def sentinel_settings():
    return object()


def test_sync_all_entities_runs_in_order(monkeypatch, sentinel_settings):
    calls: list[tuple[str, bool, int | None]] = []
    progress_events: list[tuple[str, int, int | None]] = []

    def progress_callback(entity: str, processed: int, total: int | None) -> None:
        progress_events.append((entity, processed, total))

    for entity in pipeline.DEFAULT_SYNC_SEQUENCE:
        def make_stub(name: str):
            def _stub(settings, *, full_refresh, page_size, progress_callback=None, start_datetime=None, end_datetime=None, ignore_checkpoint=False, dependency_resolver=None, dependency_max_attempts=3):
                assert settings is sentinel_settings
                calls.append((name, full_refresh, page_size))
                if progress_callback:
                    progress_callback(1, 5)
                return f"{name}-summary"
            return _stub

        stub = make_stub(entity)
        monkeypatch.setitem(pipeline._SYNC_HANDLERS, entity, stub)

    monkeypatch.setattr(pipeline, "get_settings", lambda: sentinel_settings)

    summary = pipeline.sync_all_entities(
        entities=None,
        full_refresh=False,
        page_size=25,
        progress_callback=progress_callback,
        raise_on_error=False,
    )

    assert [call[0] for call in calls] == list(pipeline.DEFAULT_SYNC_SEQUENCE)
    for _, full_refresh, page_size in calls:
        assert full_refresh is False
        assert page_size == 25
    assert summary.succeeded is True
    assert len(summary.results) == len(pipeline.DEFAULT_SYNC_SEQUENCE)
    assert progress_events == [(entity, 1, 5) for entity in pipeline.DEFAULT_SYNC_SEQUENCE]


def test_sync_all_entities_stops_on_failure(monkeypatch, sentinel_settings):
    sequence = pipeline.DEFAULT_SYNC_SEQUENCE
    calls: list[str] = []

    def make_success_stub(name: str):
        def _stub(settings, *, full_refresh, page_size, progress_callback=None, start_datetime=None, end_datetime=None, ignore_checkpoint=False, dependency_resolver=None, dependency_max_attempts=3):
            calls.append(name)
            return f"{name}-summary"
        return _stub

    for entity in sequence:
        monkeypatch.setitem(pipeline._SYNC_HANDLERS, entity, make_success_stub(entity))

    def failing_stub(settings, *, full_refresh, page_size, progress_callback=None, start_datetime=None, end_datetime=None, ignore_checkpoint=False, dependency_resolver=None, dependency_max_attempts=3):
        calls.append("samples")
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(pipeline._SYNC_HANDLERS, "samples", failing_stub)
    monkeypatch.setattr(pipeline, "get_settings", lambda: sentinel_settings)

    summary = pipeline.sync_all_entities(
        entities=None,
        raise_on_error=False,
    )

    assert summary.succeeded is False
    assert summary.failed_entity == "samples"
    assert summary.error_message == "simulated failure"
    assert [result.entity for result in summary.results] == ["customers", "orders", "samples"]
    assert all(result.succeeded for result in summary.results[:2])
    assert summary.results[-1].succeeded is False

    with pytest.raises(pipeline.SyncOrchestrationError):
        pipeline.sync_all_entities(entities=None, raise_on_error=True)


def test_sync_recent_entities_invokes_window(monkeypatch, sentinel_settings):
    captured_kwargs = {}
    fake_summary = object()

    def fake_sync_all_entities(settings_arg, **kwargs):
        assert settings_arg is sentinel_settings
        captured_kwargs.update(kwargs)
        return fake_summary

    class FakeResolver:
        def __init__(self, settings_arg):
            assert settings_arg is sentinel_settings
            self.closed = False

        def close(self) -> None:
            self.closed = True

    fake_resolver = FakeResolver(sentinel_settings)

    monkeypatch.setattr(pipeline, "get_settings", lambda: sentinel_settings)
    monkeypatch.setattr(pipeline, "sync_all_entities", fake_sync_all_entities)
    monkeypatch.setattr(pipeline, "EntityRecoveryService", lambda settings_arg: fake_resolver)

    result = pipeline.sync_recent_entities(
        lookback_days=5,
        entities=("orders",),
        page_size=10,
        dependency_max_attempts=4,
        progress_callback=None,
    )

    assert result is fake_summary
    assert fake_resolver.closed is True
    assert captured_kwargs["ignore_checkpoint"] is True
    assert captured_kwargs["dependency_resolver"] is fake_resolver
    assert captured_kwargs["dependency_max_attempts"] == 4
    assert captured_kwargs["entities"] == ("orders",)
    assert captured_kwargs["page_size"] == 10
    assert captured_kwargs["raise_on_error"] is True
    delta = captured_kwargs["end_datetime"] - captured_kwargs["start_datetime"]
    assert delta.days == 5


def test_collect_skipped_entities_groups_results():
    now = pipeline.datetime.utcnow()
    result_ok = pipeline.EntitySyncResult(
        entity="orders",
        started_at=now,
        completed_at=now,
        duration_seconds=0.0,
        succeeded=True,
        summary=type("Summary", (), {"skipped_entities": [SkippedEntity(entity_id=1, reason="missing_customer")]})(),
    )
    result_empty = pipeline.EntitySyncResult(
        entity="samples",
        started_at=now,
        completed_at=now,
        duration_seconds=0.0,
        succeeded=True,
        summary=type("Summary", (), {"skipped_entities": []})(),
    )
    summary = pipeline.SyncRunSummary(
        started_at=now,
        completed_at=now,
        succeeded=True,
        results=[result_ok, result_empty],
    )

    grouped = pipeline.collect_skipped_entities(summary)
    assert grouped["orders"][0].entity_id == 1
    assert grouped["orders"][0].reason == "missing_customer"
    assert grouped["samples"] == []

