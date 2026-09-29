"""Structured logging, Prometheus metrics and OpenTelemetry tracing in one place."""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager

import structlog
from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------- metrics

_LATENCY_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5)
_LLM_BUCKETS = (0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 8, 13, 20)

HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "route", "status"], buckets=_LATENCY_BUCKETS
)
MATCH_LATENCY = Histogram(
    "match_duration_seconds", "Time to find and atomically assign a driver", ["outcome"], buckets=_LATENCY_BUCKETS
)
MATCH_OUTCOMES = Counter("match_attempts_total", "Matching attempts by outcome", ["outcome"])
RIDES_CREATED = Counter("rides_created_total", "Rides created", ["kind", "source"])
RIDE_TRANSITIONS = Counter("ride_transitions_total", "Ride status transitions", ["to_status"])
WS_CONNECTIONS = Gauge("ws_connections", "Open WebSocket connections", ["kind"], multiprocess_mode="livesum")
DRIVER_LOCATION_UPDATES = Counter("driver_location_updates_total", "Driver location updates", ["transport"])

AGENT_LATENCY = Histogram("agent_turn_duration_seconds", "End-to-end agent turn latency", ["action"], buckets=_LLM_BUCKETS)
LLM_LATENCY = Histogram("llm_call_duration_seconds", "LLM call latency", ["model"], buckets=_LLM_BUCKETS)
LLM_CALLS = Counter("llm_calls_total", "LLM calls", ["model", "outcome"])
LLM_TOKENS = Counter("llm_tokens_total", "LLM tokens", ["model", "kind"])
LLM_COST = Counter("llm_cost_usd_total", "Estimated LLM spend (USD)", ["model"])
AGENT_TOOL_CALLS = Counter("agent_tool_calls_total", "Agent tool executions", ["tool", "outcome"])
AGENT_REPAIRS = Counter("agent_repairs_total", "Tool-call arguments rejected and sent back to the LLM", ["reason"])

# ---------------------------------------------------------------- logging


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_ids,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def _add_trace_ids(_, __, event_dict):
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
    return event_dict


def get_logger(name: str | None = None):
    return structlog.get_logger(name)


# ---------------------------------------------------------------- tracing

tracer = trace.get_tracer("campusride")


def configure_tracing(service_name: str, otlp_endpoint: str | None) -> None:
    """Export spans over OTLP/HTTP (e.g. to Jaeger) when an endpoint is configured; otherwise no-op."""
    if not otlp_endpoint:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


@contextmanager
def span(name: str, **attrs):
    with tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v)
        yield s
