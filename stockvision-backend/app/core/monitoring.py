"""
Observability wiring: Prometheus metrics + OpenTelemetry tracing.

Design decision: both are configured to degrade gracefully with no external
collector reachable (exactly this sandbox's situation — no Prometheus/OTLP
collector running) rather than crashing app startup. Prometheus metrics are
always exposed at /metrics regardless (that endpoint has no external
dependency, it just accumulates in-process counters); OpenTelemetry's OTLP
exporter is wrapped so a failed connection to the collector logs a warning
on each flush attempt instead of taking the request path down with it.
"""
import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings

logger = logging.getLogger(__name__)


def setup_prometheus(app: FastAPI) -> None:
    """Exposes GET /metrics in Prometheus text format: request counts,
    latency histograms, and in-flight request gauges, broken down by path/
    method/status — the standard prometheus_fastapi_instrumentator defaults,
    which is exactly what the docker-compose.yml `prometheus` service scrapes
    (see deploy/prometheus.yml)."""
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def setup_tracing(app: FastAPI) -> None:
    """
    Wires OpenTelemetry auto-instrumentation for every FastAPI request.

    Uses OTLP-over-HTTP so it works with any OTel-compatible collector
    (Jaeger, Tempo, Honeycomb, or the collector bundled with most cloud
    providers) without vendor-specific code. `OTEL_EXPORTER_OTLP_ENDPOINT`
    (standard OTel env var) controls where spans are sent.

    Design decision: the BatchSpanProcessor + exporter (which spins up a
    background export thread) is only created when that env var is actually
    set. Creating it unconditionally means the background thread
    continuously attempts — and fails — to reach a collector that was never
    configured (e.g. in this sandbox, or in any dev/test environment without
    one running), which is wasted work and, worse, can log confusing
    "I/O operation on closed file" errors during interpreter/test-session
    shutdown as the thread's own failure-logging races the process closing
    its log handles. Tracing is still fully wired (spans are created either
    way); we just don't attempt to export them anywhere without a destination.
    """
    resource = Resource.create({"service.name": settings.APP_NAME, "service.version": "0.1.0"})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            exporter = OTLPSpanExporter()  # reads OTEL_EXPORTER_OTLP_ENDPOINT from env
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OpenTelemetry exporting spans to %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("OTLP exporter setup failed: %s", exc)
    else:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — spans are created but not exported.")

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
