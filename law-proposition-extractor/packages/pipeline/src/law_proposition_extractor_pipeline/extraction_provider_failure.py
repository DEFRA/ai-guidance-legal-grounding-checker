"""Classify provider/billing extraction failures and enforce run-level fail-fast abort."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ProviderFailureCategory = Literal[
    "provider_billing_or_quota",
    "provider_auth",
    "provider_rate_limit",
    "provider_transport",
    "schema_or_parse",
    "model_empty_output",
    "unknown",
]

PROVIDER_FAILURE_CATEGORIES: tuple[ProviderFailureCategory, ...] = (
    "provider_billing_or_quota",
    "provider_auth",
    "provider_rate_limit",
    "provider_transport",
    "schema_or_parse",
    "model_empty_output",
    "unknown",
)

FATAL_IMMEDIATE_PROVIDER_CATEGORIES: frozenset[ProviderFailureCategory] = frozenset(
    {"provider_billing_or_quota", "provider_auth"}
)

TRANSIENT_PROVIDER_CATEGORIES: frozenset[ProviderFailureCategory] = frozenset(
    {"provider_rate_limit", "provider_transport"}
)

ABORTABLE_PROVIDER_CATEGORIES: frozenset[ProviderFailureCategory] = (
    FATAL_IMMEDIATE_PROVIDER_CATEGORIES | TRANSIENT_PROVIDER_CATEGORIES
)

BENCHMARK_VERDICT_INCOMPLETE = "failed_incomplete_extraction"


def classify_provider_extraction_failure(message: str | None) -> ProviderFailureCategory:
    """Map an error message to a coarse provider / parse failure category."""
    blob = (message or "").lower()
    if not blob.strip():
        return "unknown"

    if any(
        s in blob
        for s in (
            "credit balance",
            "insufficient credit",
            "not enough credit",
            "purchase credits",
            "billing to upgrade",
            "plans & billing",
            "insufficient_quota",
            "insufficient quota",
            "exceeded your current quota",
            "quota exceeded",
            "billing hard limit",
            "payment required",
        )
    ):
        return "provider_billing_or_quota"

    if any(
        s in blob
        for s in (
            "invalid api key",
            "incorrect api key",
            "authentication",
            "unauthorized",
            "permission denied",
            "access denied",
            "invalid x-api-key",
            "api key not valid",
        )
    ):
        return "provider_auth"

    if any(s in blob for s in ("rate limit", "ratelimit", "429", "too many requests")):
        return "provider_rate_limit"

    if any(
        s in blob
        for s in (
            "overloaded",
            "unavailable",
            "connection error",
            "connection refused",
            "timed out",
            "timeout",
            "service unavailable",
            "502",
            "503",
            "504",
            "bad gateway",
            "gateway timeout",
            "provider returned no content",
            "transport",
        )
    ):
        return "provider_transport"

    if any(
        s in blob
        for s in (
            "json parse",
            "jsondecode",
            "schema validation",
            "validation failed",
            "extraction_schema_violation",
            "extraction schema violation",
            "violates json schema",
            "non-json",
            "unparseable json",
        )
    ):
        return "schema_or_parse"

    if any(
        s in blob
        for s in (
            "model returned no propositions",
            "returned no propositions",
            "propositions=[]",
            "parsed_empty",
            "empty model response",
            "no extractable atoms",
            "validation removed all",
        )
    ):
        return "model_empty_output"

    if "api error" in blob or "api_error" in blob:
        return "provider_transport"

    return "unknown"


def is_abortable_provider_category(category: ProviderFailureCategory) -> bool:
    return category in ABORTABLE_PROVIDER_CATEGORIES


@dataclass(frozen=True)
class ProviderFailureAbortPolicy:
    """Run-level thresholds for aborting extraction after provider failures."""

    enabled: bool = True
    consecutive_transient_threshold: int = 5
    failure_rate_threshold: float = 0.20
    min_attempted_jobs_for_rate: int = 20
    max_failed_extraction_jobs: int | None = None


DEFAULT_PROVIDER_FAILURE_ABORT_POLICY = ProviderFailureAbortPolicy()


def resolve_provider_failure_abort_policy(
    *,
    abort_on_provider_failure: bool | None = None,
    provider_failure_threshold: int | None = None,
    max_failed_extraction_jobs: int | None = None,
    case_data: dict[str, Any] | None = None,
) -> ProviderFailureAbortPolicy:
    """Merge CLI flags with optional case ``extraction.provider_failure_abort`` block."""
    enabled = True if abort_on_provider_failure is None else bool(abort_on_provider_failure)
    consecutive = DEFAULT_PROVIDER_FAILURE_ABORT_POLICY.consecutive_transient_threshold
    max_failed = max_failed_extraction_jobs
    if isinstance(case_data, dict):
        extraction = case_data.get("extraction")
        if isinstance(extraction, dict):
            block = extraction.get("provider_failure_abort")
            if isinstance(block, dict):
                if abort_on_provider_failure is None and block.get("enabled") is not None:
                    enabled = bool(block.get("enabled"))
                if provider_failure_threshold is None:
                    raw_thr = block.get("consecutive_threshold") or block.get(
                        "provider_failure_threshold"
                    )
                    if isinstance(raw_thr, int) and raw_thr > 0:
                        consecutive = raw_thr
                if max_failed is None and block.get("max_failed_extraction_jobs") is not None:
                    raw_max = block.get("max_failed_extraction_jobs")
                    if isinstance(raw_max, int) and raw_max > 0:
                        max_failed = raw_max
    if provider_failure_threshold is not None and provider_failure_threshold > 0:
        consecutive = provider_failure_threshold
    return ProviderFailureAbortPolicy(
        enabled=enabled,
        consecutive_transient_threshold=consecutive,
        failure_rate_threshold=DEFAULT_PROVIDER_FAILURE_ABORT_POLICY.failure_rate_threshold,
        min_attempted_jobs_for_rate=DEFAULT_PROVIDER_FAILURE_ABORT_POLICY.min_attempted_jobs_for_rate,
        max_failed_extraction_jobs=max_failed,
    )


@dataclass
class ProviderFailureAbortTracker:
    policy: ProviderFailureAbortPolicy = field(default_factory=ProviderFailureAbortPolicy)
    attempted_selected_jobs: int = 0
    failed_selected_jobs: int = 0
    consecutive_transient_failures: int = 0
    last_transient_category: ProviderFailureCategory | None = None
    abort_metadata: dict[str, Any] | None = None

    @property
    def aborted(self) -> bool:
        return self.abort_metadata is not None

    def record_selected_job_success(self) -> None:
        self.attempted_selected_jobs += 1
        self.consecutive_transient_failures = 0
        self.last_transient_category = None

    def record_selected_job_without_provider_failure(self) -> None:
        """Job ran but did not surface a classified provider failure (may still have 0 props)."""
        self.attempted_selected_jobs += 1
        self.consecutive_transient_failures = 0
        self.last_transient_category = None

    def record_provider_failure(
        self,
        *,
        category: ProviderFailureCategory,
        message: str,
        source_record_id: str,
        source_fragment_id: str | None,
        extraction_job_id: str,
    ) -> bool:
        """Record a provider-classified failure; return True when the run should abort now."""
        if not self.policy.enabled or self.aborted:
            return self.aborted

        self.attempted_selected_jobs += 1
        self.failed_selected_jobs += 1

        if category in TRANSIENT_PROVIDER_CATEGORIES:
            if category == self.last_transient_category:
                self.consecutive_transient_failures += 1
            else:
                self.last_transient_category = category
                self.consecutive_transient_failures = 1

        reason = self._evaluate_abort(
            category=category,
            message=message,
            source_record_id=source_record_id,
            source_fragment_id=source_fragment_id,
            extraction_job_id=extraction_job_id,
        )
        if reason is not None:
            self._set_abort(
                reason,
                category=category,
                message=message,
                source_record_id=source_record_id,
                source_fragment_id=source_fragment_id,
                extraction_job_id=extraction_job_id,
            )
            return True
        return False

    def _evaluate_abort(
        self,
        *,
        category: ProviderFailureCategory,
        message: str,
        source_record_id: str,
        source_fragment_id: str | None,
        extraction_job_id: str,
    ) -> str | None:
        if category in FATAL_IMMEDIATE_PROVIDER_CATEGORIES:
            return "fatal_provider_error"

        max_failed = self.policy.max_failed_extraction_jobs
        if max_failed is not None and self.failed_selected_jobs >= max_failed:
            return "max_failed_extraction_jobs"

        if (
            category in TRANSIENT_PROVIDER_CATEGORIES
            and self.consecutive_transient_failures >= self.policy.consecutive_transient_threshold
        ):
            return "consecutive_transient_provider_failures"

        attempted = self.attempted_selected_jobs
        if attempted >= self.policy.min_attempted_jobs_for_rate:
            rate = self.failed_selected_jobs / attempted
            if rate > self.policy.failure_rate_threshold:
                return "provider_failure_rate_exceeded"

        return None

    def _set_abort(
        self,
        abort_reason: str,
        *,
        category: ProviderFailureCategory,
        message: str,
        source_record_id: str,
        source_fragment_id: str | None,
        extraction_job_id: str,
    ) -> None:
        self.abort_metadata = build_extraction_abort_metadata(
            failure_reason=category,
            abort_reason=abort_reason,
            failed_extraction_jobs=self.failed_selected_jobs,
            attempted_extraction_jobs=self.attempted_selected_jobs,
            last_provider_error_message=message,
            source_record_id=source_record_id,
            source_fragment_id=source_fragment_id,
            extraction_job_id=extraction_job_id,
            policy=self.policy,
        )


def build_extraction_abort_metadata(
    *,
    failure_reason: ProviderFailureCategory,
    abort_reason: str,
    failed_extraction_jobs: int,
    attempted_extraction_jobs: int,
    last_provider_error_message: str,
    source_record_id: str,
    source_fragment_id: str | None,
    extraction_job_id: str,
    policy: ProviderFailureAbortPolicy,
) -> dict[str, Any]:
    return {
        "aborted": True,
        "run_status": "failed",
        "failure_reason": failure_reason,
        "abort_reason": abort_reason,
        "failed_extraction_jobs": failed_extraction_jobs,
        "attempted_extraction_jobs": attempted_extraction_jobs,
        "last_provider_error_message": last_provider_error_message[:2000],
        "abort_source_record_id": source_record_id,
        "abort_source_fragment_id": source_fragment_id,
        "abort_extraction_job_id": extraction_job_id,
        "export_not_benchmarkable": True,
        "export_incomplete": True,
        "benchmark_verdict": BENCHMARK_VERDICT_INCOMPLETE,
        "policy": asdict(policy),
    }


def collect_job_failure_messages(
    *,
    job_row: dict[str, Any],
    outcome: Any | None,
    trace_rows: list[dict[str, Any]],
) -> list[str]:
    messages: list[str] = []
    if outcome is not None:
        fr = getattr(outcome, "failure_reason", None)
        if fr:
            messages.append(str(fr))
        for err in getattr(outcome, "validation_errors", None) or []:
            if str(err).strip():
                messages.append(str(err))
        halt = getattr(outcome, "repairable_extraction_halt_reason", None)
        if halt:
            messages.append(str(halt))
    for key in ("errors", "warnings", "parse_error_message"):
        raw = job_row.get(key)
        if isinstance(raw, list):
            messages.extend(str(x) for x in raw if str(x).strip())
        elif raw is not None and str(raw).strip():
            messages.append(str(raw))
    for row in trace_rows:
        if not isinstance(row, dict):
            continue
        for key in ("model_error", "failure_reason", "error", "skip_reason"):
            val = row.get(key)
            if val is not None and str(val).strip():
                messages.append(str(val))
    return messages


def classify_job_provider_failure(messages: Iterable[str]) -> tuple[ProviderFailureCategory | None, str]:
    best: ProviderFailureCategory | None = None
    best_msg = ""
    priority = {
        "provider_billing_or_quota": 0,
        "provider_auth": 1,
        "provider_rate_limit": 2,
        "provider_transport": 3,
    }
    for msg in messages:
        cat = classify_provider_extraction_failure(msg)
        if not is_abortable_provider_category(cat):
            continue
        if best is None or priority.get(cat, 99) < priority.get(best, 99):
            best = cat
            best_msg = msg
    return best, best_msg


def job_had_provider_failure(
    *,
    job_row: dict[str, Any],
    outcome: Any | None,
    trace_rows: list[dict[str, Any]],
) -> tuple[ProviderFailureCategory | None, str]:
    if not job_row.get("selected_for_extraction"):
        return None, ""
    llm_invoked = bool(job_row.get("llm_invoked"))
    live_failed = any(
        isinstance(row, dict)
        and row.get("llm_call_succeeded") is False
        and (row.get("model_error") or row.get("failure_reason"))
        for row in trace_rows
    )
    has_errors = bool(job_row.get("errors")) or bool(getattr(outcome, "failed_closed", False))
    halt = bool(getattr(outcome, "repairable_extraction_halt", False))
    if not llm_invoked and not live_failed and not has_errors and not halt:
        return None, ""
    messages = collect_job_failure_messages(job_row=job_row, outcome=outcome, trace_rows=trace_rows)
    return classify_job_provider_failure(messages)


def attach_extraction_abort_to_bundle(bundle: dict[str, Any], abort_metadata: dict[str, Any]) -> None:
    bundle["extraction_abort_metadata"] = abort_metadata
    bundle["run_status"] = abort_metadata.get("run_status", "failed")
    bundle["failure_reason"] = abort_metadata.get("failure_reason")
    bundle["export_incomplete"] = True
    bundle["export_not_benchmarkable"] = True
    bundle["benchmark_verdict"] = abort_metadata.get("benchmark_verdict", BENCHMARK_VERDICT_INCOMPLETE)


def extraction_abort_metadata_from_bundle(bundle: dict[str, Any]) -> dict[str, Any] | None:
    raw = bundle.get("extraction_abort_metadata")
    return raw if isinstance(raw, dict) and raw.get("aborted") else None


def assess_extraction_benchmark_completeness(bundle: dict[str, Any]) -> dict[str, Any]:
    """
    Determine whether extraction produced a benchmarkable export.

    Uses persisted abort metadata when present; otherwise infers from jobs/traces.
    """
    abort = extraction_abort_metadata_from_bundle(bundle)
    if abort is not None:
        sources_zero = _sources_with_zero_propositions(bundle)
        return {
            "incomplete": True,
            "inferred": False,
            "benchmark_verdict": abort.get("benchmark_verdict", BENCHMARK_VERDICT_INCOMPLETE),
            "failure_reason": abort.get("failure_reason"),
            "failed_extraction_jobs": int(abort.get("failed_extraction_jobs") or 0),
            "attempted_extraction_jobs": int(abort.get("attempted_extraction_jobs") or 0),
            "last_provider_error_message": abort.get("last_provider_error_message"),
            "sources_with_zero_propositions": sources_zero,
            "source_coverage_incomplete": bool(sources_zero),
            "extraction_job_failure_count": _count_failed_extraction_jobs(bundle),
            "abort_metadata": abort,
        }

    jobs = [row for row in (bundle.get("proposition_extraction_jobs") or []) if isinstance(row, dict)]
    selected_jobs = [j for j in jobs if j.get("selected_for_extraction")]
    attempted = sum(1 for j in selected_jobs if j.get("started_at") or j.get("llm_invoked"))
    failed_jobs = _count_failed_extraction_jobs(bundle)
    billing_traces = _count_llm_traces_with_category(bundle, "provider_billing_or_quota")
    auth_traces = _count_llm_traces_with_category(bundle, "provider_auth")
    sources_zero = _sources_with_zero_propositions(bundle)

    rate_exceeded = False
    if attempted >= DEFAULT_PROVIDER_FAILURE_ABORT_POLICY.min_attempted_jobs_for_rate:
        rate = failed_jobs / max(attempted, 1)
        rate_exceeded = rate > DEFAULT_PROVIDER_FAILURE_ABORT_POLICY.failure_rate_threshold

    inferred_reason: ProviderFailureCategory | None = None
    if billing_traces > 0:
        inferred_reason = "provider_billing_or_quota"
    elif auth_traces > 0:
        inferred_reason = "provider_auth"
    elif rate_exceeded and failed_jobs >= DEFAULT_PROVIDER_FAILURE_ABORT_POLICY.consecutive_transient_threshold:
        inferred_reason = "provider_transport"

    incomplete = bool(
        inferred_reason is not None
        and (
            billing_traces > 0
            or auth_traces > 0
            or (rate_exceeded and sources_zero)
        )
    )

    return {
        "incomplete": incomplete,
        "inferred": incomplete,
        "benchmark_verdict": BENCHMARK_VERDICT_INCOMPLETE if incomplete else "ok",
        "failure_reason": inferred_reason,
        "failed_extraction_jobs": failed_jobs,
        "attempted_extraction_jobs": attempted,
        "last_provider_error_message": _last_provider_error_message(bundle),
        "sources_with_zero_propositions": sources_zero,
        "source_coverage_incomplete": bool(sources_zero) and incomplete,
        "extraction_job_failure_count": failed_jobs,
        "billing_error_trace_count": billing_traces,
        "abort_metadata": None,
    }


def is_export_blocked_for_incomplete_extraction(bundle: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    assessment = assess_extraction_benchmark_completeness(bundle)
    return bool(assessment.get("incomplete")), assessment


def _count_failed_extraction_jobs(bundle: dict[str, Any]) -> int:
    jobs = bundle.get("proposition_extraction_jobs") or []
    count = 0
    for job in jobs:
        if not isinstance(job, dict) or not job.get("selected_for_extraction"):
            continue
        if job.get("errors") or (
            job.get("llm_invoked")
            and int(job.get("proposition_count") or 0) == 0
            and str(job.get("cache_status") or "") != "content_hash_reuse"
        ):
            count += 1
    return count


def _sources_with_zero_propositions(bundle: dict[str, Any]) -> list[str]:
    sources = bundle.get("source_records") or bundle.get("sources") or []
    source_ids = [str(s.get("id")) for s in sources if isinstance(s, dict) and s.get("id")]
    if not source_ids:
        return []
    counts: dict[str, int] = {sid: 0 for sid in source_ids}
    for prop in bundle.get("propositions") or []:
        if not isinstance(prop, dict):
            continue
        sid = str(prop.get("source_record_id") or "").strip()
        if sid in counts:
            counts[sid] += 1
    return sorted(sid for sid, n in counts.items() if n == 0)


def _count_llm_traces_with_category(
    bundle: dict[str, Any], category: ProviderFailureCategory
) -> int:
    from .extraction_llm_metrics import extraction_llm_call_traces_from_bundle

    traces = extraction_llm_call_traces_from_bundle(bundle)
    count = 0
    for row in traces:
        if not isinstance(row, dict):
            continue
        if row.get("llm_call_succeeded") is True:
            continue
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("model_error", "failure_reason", "error", "skip_reason")
        )
        if classify_provider_extraction_failure(blob) == category:
            count += 1
    return count


def _last_provider_error_message(bundle: dict[str, Any]) -> str | None:
    from .extraction_llm_metrics import extraction_llm_call_traces_from_bundle

    last: str | None = None
    for row in extraction_llm_call_traces_from_bundle(bundle):
        if not isinstance(row, dict):
            continue
        for key in ("model_error", "failure_reason", "error"):
            val = row.get(key)
            if val and str(val).strip():
                msg = str(val).strip()
                cat = classify_provider_extraction_failure(msg)
                if is_abortable_provider_category(cat):
                    last = msg
    return last
