"""Tracing and metrics (SPEC §21). One Lingard ``trace_id`` per scene is attached to every span and LLM call."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter

TRACE_ATTR = "lingard.trace_id"
_configured = False


def setup(service: str, exporter: SpanExporter | None = None) -> None:
    """Idempotent. Exports via OTLP when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, or to the given exporter (tests)."""
    global _configured
    if _configured:
        return
    resource = Resource.create({"service.name": f"lingard-{service}"})
    provider = TracerProvider(resource=resource)
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    metrics.set_meter_provider(MeterProvider(resource=resource))
    _configured = True


@contextmanager
def span(name: str, trace_id: str | None = None, **attributes: Any) -> Iterator[trace.Span]:
    tracer = trace.get_tracer("lingard")
    with tracer.start_as_current_span(name) as current:
        if trace_id:
            current.set_attribute(TRACE_ATTR, trace_id)
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(f"lingard.{key}", value)
        yield current


def meter() -> metrics.Meter:
    return metrics.get_meter("lingard")


def langfuse_handler(trace_id: str | None = None, **metadata: Any) -> Any | None:
    """LangChain callback for self-hosted Langfuse, or None when not configured or not installed."""
    if not os.environ.get("LANGFUSE_HOST"):
        return None
    try:
        from langfuse.callback import CallbackHandler
    except ImportError:
        return None
    return CallbackHandler(session_id=trace_id, metadata=metadata)
