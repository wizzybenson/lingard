from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import lingard_telemetry as telemetry


def test_span_carries_lingard_trace_id() -> None:
    exporter = InMemorySpanExporter()
    telemetry.setup("test", exporter=exporter)
    with telemetry.span("actor.turn", trace_id="abc", scene="s1", skipped=None):
        pass
    [finished] = [s for s in exporter.get_finished_spans() if s.name == "actor.turn"]
    assert finished.attributes is not None
    assert finished.attributes[telemetry.TRACE_ATTR] == "abc"
    assert finished.attributes["lingard.scene"] == "s1"
    assert "lingard.skipped" not in finished.attributes


def test_langfuse_absent_without_config(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    assert telemetry.langfuse_handler("t") is None
