"""Prometheus metrics for the scan service."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

_SCAN_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300)
_REQUEST_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


class Metrics:
    """All service metrics, registered on one registry."""

    def __init__(self, registry: CollectorRegistry):
        """Register every metric on registry."""
        self.registry = registry
        self.scans = Counter(
            "llm_tool_guard_scans_total",
            "Model scans by verdict (clean, flagged, error)",
            ["verdict"],
            registry=registry,
        )
        self.flagged = Counter(
            "llm_tool_guard_flagged_total",
            "Hashes returned as flagged, by reason (verdict, over_limit, hash_mismatch, error)",
            ["reason"],
            registry=registry,
        )
        self.over_limit = Counter(
            "llm_tool_guard_over_limit_total",
            "Items or requests over a limit (text_bytes, queue, body)",
            ["limit"],
            registry=registry,
        )
        self.cache_hits = Counter("llm_tool_guard_cache_hits_total", "Verdict cache hits", registry=registry)
        self.cache_misses = Counter("llm_tool_guard_cache_misses_total", "Verdict cache misses", registry=registry)
        self.cache_errors = Counter(
            "llm_tool_guard_cache_errors_total",
            "Failed verdict cache calls (get, set)",
            ["operation"],
            registry=registry,
        )
        self.cache_up = Gauge(
            "llm_tool_guard_cache_up", "1 when the last verdict cache call succeeded", registry=registry
        )
        self.scan_seconds = Histogram(
            "llm_tool_guard_scan_duration_seconds", "Model scan time per text", buckets=_SCAN_BUCKETS, registry=registry
        )
        self.request_seconds = Histogram(
            "llm_tool_guard_request_duration_seconds",
            "Time to answer a scan request",
            buckets=_REQUEST_BUCKETS,
            registry=registry,
        )
        self.pending_scans = Gauge("llm_tool_guard_pending_scans", "Texts queued or being scanned", registry=registry)
        self.ready = Gauge("llm_tool_guard_ready", "1 once the model has loaded", registry=registry)
        for verdict in ("clean", "flagged", "error"):
            self.scans.labels(verdict)
        for reason in ("verdict", "over_limit", "hash_mismatch", "error"):
            self.flagged.labels(reason)
        for limit in ("text_bytes", "queue", "body"):
            self.over_limit.labels(limit)
        for operation in ("get", "set"):
            self.cache_errors.labels(operation)
