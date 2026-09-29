from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn

import typer
from dotenv import load_dotenv
from pydantic import ValidationError

from law_discovery.ai import (
    AdaAIConfigurationError,
    CategoryExpansion,
    expand_category_with_ai,
    load_ai_settings,
    run_ai_connection_check,
)
from law_discovery.category_profiles import passes_category_anchor
from law_discovery.console import DiscoveryConsole, OutputMode
from law_discovery.discovery_service import DiscoveryService
from law_discovery.export import (
    save_selected_sources_for_judit,
    save_source_bundle_for_judit,
)
from law_discovery.lex_adapter import LexAdapter, LexAdapterError
from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    DiscoveryRun,
    SourceBundle,
    SourceRegister,
    load_category_brief,
    load_discovery_run,
    load_related_source_expansion_run,
    load_source_bundle,
    load_source_register,
    save_discovery_run,
    save_related_source_expansion_run,
    save_source_bundle,
    save_source_register,
)
from law_discovery.query_plan import build_query_plan, query_plan_to_jsonable
from law_discovery.related_query_plan import ExpansionProfile
from law_discovery.related_source_service import RelatedSourceExpansionService, SeedSourceType
from law_discovery.law_proposition_extractor_intake_bundle import format_law_proposition_extractor_intake_summary, make_law_proposition_extractor_intake_bundle
from law_discovery.source_bundle import build_source_bundle
from law_discovery.triage_helpers import ai_register_review_status, discovery_run_has_ai_triage

app = typer.Typer(
    name="law-discovery",
    help="Law Discovery — UK legal source discovery workbench (standalone from Law Proposition Extractor and Proposition Matcher).",
    no_args_is_help=True,
)


def _fail(message: str, *, code: int = 1) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=code)


def _write_json(payload: Any, output: Path | None) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{text}\n", encoding="utf-8")
    else:
        typer.echo(text)


def _load_expansion(path: Path | None) -> CategoryExpansion | None:
    if path is None:
        return None
    if not path.exists():
        _fail(f"Expansion file not found: {path}")
    try:
        return CategoryExpansion.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        _fail(f"Invalid CategoryExpansion JSON in {path}: {exc}")


def _load_category(path: Path) -> CategoryBrief:
    if not path.exists():
        _fail(f"Category file not found: {path}")
    try:
        return load_category_brief(path)
    except ValidationError as exc:
        _fail(f"Invalid CategoryBrief JSON in {path}: {exc}")


_NO_AI_TRIAGE_MESSAGE = (
    "This discovery run has no AI triage metadata. "
    "Use --accept-high-confidence or rerun discover with --use-ai-triage."
)

_AUTO_ACCEPT_WARNING_THRESHOLD = 50


def _high_confidence_acceptance_plan(run: DiscoveryRun) -> dict[str, Any]:
    anchor_pass = 0
    anchor_fail = 0
    auto_accepted: list[CandidateSource] = []

    for candidate in run.candidate_sources:
        if candidate.confidence != "high":
            continue
        if passes_category_anchor(candidate, run.category.category_id):
            anchor_pass += 1
            auto_accepted.append(candidate)
        else:
            anchor_fail += 1

    return {
        "high_confidence_anchor_pass": anchor_pass,
        "high_confidence_anchor_fail": anchor_fail,
        "auto_accepted": auto_accepted,
    }


def _make_register_from_run(
    run: DiscoveryRun,
    *,
    accept_high_confidence: bool,
    accept_ai_likely_accept: bool,
) -> SourceRegister:
    if accept_high_confidence and accept_ai_likely_accept:
        _fail("Use either --accept-high-confidence or --accept-ai-likely-accept, not both.")

    if accept_ai_likely_accept:
        if not discovery_run_has_ai_triage(run.candidate_sources):
            _fail(_NO_AI_TRIAGE_MESSAGE)
        return _make_register_from_ai_triage(run)

    acceptance_plan = _high_confidence_acceptance_plan(run)
    accepted_sources = []
    parked_sources = []
    held_for_review = 0

    for candidate in run.candidate_sources:
        if accept_high_confidence and candidate.confidence == "high":
            if passes_category_anchor(candidate, run.category.category_id):
                accepted_sources.append(candidate.model_copy(update={"review_status": "accepted"}))
            else:
                held_for_review += 1
                parked_sources.append(
                    candidate.model_copy(update={"review_status": "needs_more_research"})
                )
        else:
            parked_sources.append(candidate.model_copy(update={"review_status": "parked"}))

    return SourceRegister(
        register_id=f"law-discovery-register-{run.category.category_id}",
        category_id=run.category.category_id,
        created_at=datetime.now(tz=UTC),
        accepted_sources=accepted_sources,
        rejected_sources=[],
        parked_sources=parked_sources,
        metadata={
            "discovery_run_id": run.run_id,
            "accept_high_confidence": accept_high_confidence,
            "accept_ai_likely_accept": False,
            "candidate_count": len(run.candidate_sources),
            "high_confidence_anchor_pass": acceptance_plan["high_confidence_anchor_pass"],
            "high_confidence_anchor_fail": acceptance_plan["high_confidence_anchor_fail"],
            "auto_accepted": len(accepted_sources) if accept_high_confidence else 0,
            "held_for_review": held_for_review,
        },
    )


def _make_register_from_ai_triage(run: DiscoveryRun) -> SourceRegister:
    accepted_sources = []
    rejected_sources = []
    parked_sources = []

    for candidate in run.candidate_sources:
        if candidate.ai_triage is None:
            parked_sources.append(candidate.model_copy(update={"review_status": "parked"}))
            continue
        status = ai_register_review_status(candidate)
        updated = candidate.model_copy(update={"review_status": status})
        if status == "accepted":
            accepted_sources.append(updated)
        elif status == "rejected":
            rejected_sources.append(updated)
        else:
            parked_sources.append(updated)

    return SourceRegister(
        register_id=f"law-discovery-register-{run.category.category_id}",
        category_id=run.category.category_id,
        created_at=datetime.now(tz=UTC),
        accepted_sources=accepted_sources,
        rejected_sources=rejected_sources,
        parked_sources=parked_sources,
        metadata={
            "discovery_run_id": run.run_id,
            "accept_high_confidence": False,
            "accept_ai_likely_accept": True,
            "candidate_count": len(run.candidate_sources),
        },
    )


@app.command("check-ai")
def check_ai_cmd(
    model: Annotated[str | None, typer.Option("--model", help="AI model name override")] = None,
    litellm_base_url: Annotated[
        str | None,
        typer.Option("--litellm-base-url", help="LiteLLM base URL override"),
    ] = None,
    litellm_api_key: Annotated[
        str | None,
        typer.Option("--litellm-api-key", help="LiteLLM API key override"),
    ] = None,
) -> None:
    """Smoke-test the configured Pydantic AI → LiteLLM connection."""
    try:
        ai_settings = load_ai_settings(
            model_name=model,
            base_url=litellm_base_url,
            api_key=litellm_api_key,
        )
    except AdaAIConfigurationError as exc:
        _fail(
            "AI configuration is required for check-ai. "
            f"Set LAW_DISCOVERY_AI_MODEL and LAW_DISCOVERY_LITELLM_BASE_URL (and optionally LAW_DISCOVERY_LITELLM_API_KEY). "
            f"Details: {exc}"
        )

    typer.echo(f"Model: {ai_settings.model}")
    typer.echo(f"LiteLLM base URL: {ai_settings.litellm_base_url}")

    try:
        response = run_ai_connection_check(ai_settings)
    except Exception as exc:  # noqa: BLE001 - user-facing CLI error
        _fail(f"AI connection check failed: {type(exc).__name__}: {exc}")

    if not response.ok or response.message != "hello":
        _fail(
            "AI connection check returned an unexpected response: "
            f"{response.model_dump_json()}"
        )

    typer.secho("AI connection check passed.", fg=typer.colors.GREEN)
    typer.echo(response.model_dump_json())


@app.command("build-query-plan")
def build_query_plan_cmd(
    category_json: Annotated[Path, typer.Argument(help="Path to category brief JSON")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write query plan JSON to file"),
    ] = None,
    expansion: Annotated[
        Path | None,
        typer.Option("--expansion", help="Optional CategoryExpansion JSON"),
    ] = None,
) -> None:
    """Build a deterministic discovery query plan from a category brief."""
    category = _load_category(category_json)
    expansion_obj = _load_expansion(expansion)
    query_plan = build_query_plan(category, expansion=expansion_obj)
    _write_json(query_plan_to_jsonable(query_plan), output)


@app.command("expand-category")
def expand_category_cmd(
    category_json: Annotated[Path, typer.Argument(help="Path to category brief JSON")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Write CategoryExpansion JSON")],
    model: Annotated[str | None, typer.Option("--model", help="AI model name override")] = None,
    litellm_base_url: Annotated[
        str | None,
        typer.Option("--litellm-base-url", help="LiteLLM base URL override"),
    ] = None,
    litellm_api_key: Annotated[
        str | None,
        typer.Option("--litellm-api-key", help="LiteLLM API key override"),
    ] = None,
) -> None:
    """Expand a category brief using AI (requires LiteLLM configuration)."""
    category = _load_category(category_json)
    try:
        expansion_result = expand_category_with_ai(
            category,
            model_name=model,
            base_url=litellm_base_url,
            api_key=litellm_api_key,
        )
    except AdaAIConfigurationError as exc:
        _fail(
            "AI configuration is required for expand-category. "
            f"Set LAW_DISCOVERY_AI_MODEL and LAW_DISCOVERY_LITELLM_BASE_URL (and optionally LAW_DISCOVERY_LITELLM_API_KEY). "
            f"Details: {exc}"
        )
    except Exception as exc:  # noqa: BLE001 - user-facing CLI error
        _fail(f"Category expansion failed: {exc}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{expansion_result.model_dump_json(indent=2)}\n", encoding="utf-8")


@app.command("discover")
def discover_cmd(
    category_json: Annotated[Path, typer.Argument(help="Path to category brief JSON")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Write DiscoveryRun JSON")],
    limit_per_query: Annotated[
        int,
        typer.Option("--limit-per-query", min=1, help="Max Lex results per query"),
    ] = 10,
    no_network: Annotated[
        bool,
        typer.Option("--no-network", help="Skip Lex network discovery"),
    ] = False,
    lex_base_url: Annotated[
        str | None,
        typer.Option("--lex-base-url", help="Lex API base URL override"),
    ] = None,
    lex_api_key: Annotated[
        str | None,
        typer.Option("--lex-api-key", help="Lex API key override"),
    ] = None,
    expansion: Annotated[
        Path | None,
        typer.Option("--expansion", help="Optional CategoryExpansion JSON"),
    ] = None,
    use_ai_assessment: Annotated[
        bool,
        typer.Option("--use-ai-assessment", help="Run AI relevance assessment after scoring"),
    ] = False,
    use_ai_triage: Annotated[
        bool,
        typer.Option(
            "--use-ai-triage",
            help="Run AI batch triage after scoring to refine confidence and notes",
        ),
    ] = False,
    ai_triage_batch_size: Annotated[
        int,
        typer.Option(
            "--ai-triage-batch-size",
            min=1,
            help="Candidates per AI triage batch",
        ),
    ] = 15,
    apply_ai_review_status: Annotated[
        bool,
        typer.Option(
            "--apply-ai-review-status",
            help="Apply AI recommended review_status (default: only adjust confidence/notes)",
        ),
    ] = False,
    model: Annotated[str | None, typer.Option("--model", help="AI model name override")] = None,
    litellm_base_url: Annotated[
        str | None,
        typer.Option("--litellm-base-url", help="LiteLLM base URL override"),
    ] = None,
    litellm_api_key: Annotated[
        str | None,
        typer.Option("--litellm-api-key", help="LiteLLM API key override"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress progress output (still writes JSON)"),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option("--plain", help="Plain line-based progress without colours or bars"),
    ] = False,
) -> None:
    """Discover candidate sources for a category."""
    if quiet and plain:
        _fail("Use either --quiet or --plain, not both.")

    mode = OutputMode.QUIET if quiet else (OutputMode.PLAIN if plain else OutputMode.RICH)
    ui = DiscoveryConsole(mode)

    ui.emit("load_category", "Loading category...")
    category = _load_category(category_json)
    ui.emit("load_category", f"Loaded category: {category.label}")

    if expansion is not None:
        ui.emit("load_expansion", f"Loading expansion from {expansion}...")
    else:
        ui.emit("load_expansion", "No expansion file provided")
    expansion_obj = _load_expansion(expansion)
    if expansion_obj is not None:
        ui.emit("load_expansion", "Loaded category expansion")

    use_network = not no_network
    lex_adapter = None
    resolved_lex_base_url: str | None = None
    if use_network:
        lex_adapter = LexAdapter(base_url=lex_base_url, api_key=lex_api_key)
        resolved_lex_base_url = lex_adapter.base_url or None

    resolved_ai_model = model
    resolved_ai_base_url = litellm_base_url
    if use_ai_assessment or use_ai_triage:
        try:
            ai_settings = load_ai_settings(
                model_name=model,
                base_url=litellm_base_url,
                api_key=litellm_api_key,
            )
            resolved_ai_model = ai_settings.model
            resolved_ai_base_url = ai_settings.litellm_base_url
        except AdaAIConfigurationError:
            pass

    ui.show_startup_panel(
        category=category,
        output=output,
        use_network=use_network,
        lex_base_url=resolved_lex_base_url,
        use_ai_assessment=use_ai_assessment,
        use_ai_triage=use_ai_triage,
        ai_triage_batch_size=ai_triage_batch_size,
        ai_model=resolved_ai_model,
        ai_base_url=resolved_ai_base_url,
        expansion_path=expansion,
    )

    service = DiscoveryService(lex_adapter=lex_adapter)
    run: DiscoveryRun
    try:
        run = service.run_discovery(
            category,
            limit_per_query=limit_per_query,
            use_network=use_network,
            expansion=expansion_obj,
            use_ai_assessment=use_ai_assessment,
            use_ai_triage=use_ai_triage,
            ai_triage_batch_size=ai_triage_batch_size,
            apply_ai_review_status=apply_ai_review_status,
            ai_model_name=model,
            litellm_base_url=litellm_base_url,
            litellm_api_key=litellm_api_key,
            progress_callback=ui.handle_progress,
        )
    except AdaAIConfigurationError as exc:
        ai_flags = []
        if use_ai_assessment:
            ai_flags.append("--use-ai-assessment")
        if use_ai_triage:
            ai_flags.append("--use-ai-triage")
        ui.fail(
            f"AI configuration is required when {' or '.join(ai_flags)} is set. "
            f"Details: {exc}"
        )
    except LexAdapterError as exc:
        ui.fail(f"Lex discovery failed: {exc}")

    ui.emit("write_output", f"Writing output to {output}...")
    save_discovery_run(run, output)
    ui.show_summary(run, output)
    ui.show_warnings(run)


@app.command("make-register")
def make_register_cmd(
    discovery_run_json: Annotated[Path, typer.Argument(help="Path to DiscoveryRun JSON")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Write SourceRegister JSON")],
    accept_high_confidence: Annotated[
        bool,
        typer.Option(
            "--accept-high-confidence",
            help="Place high-confidence candidates in accepted_sources (deterministic scoring)",
        ),
    ] = False,
    accept_ai_likely_accept: Annotated[
        bool,
        typer.Option(
            "--accept-ai-likely-accept",
            help="Bucket candidates by AI triage review_priority and recommended_action",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Confirm bulk auto-accept when more than 50 high-confidence sources would be accepted",
        ),
    ] = False,
) -> None:
    """Create a source register from a discovery run."""
    if not discovery_run_json.exists():
        _fail(f"Discovery run file not found: {discovery_run_json}")
    run: DiscoveryRun
    try:
        run = load_discovery_run(discovery_run_json)
    except ValidationError as exc:
        _fail(f"Invalid DiscoveryRun JSON in {discovery_run_json}: {exc}")

    if accept_high_confidence and not yes:
        plan = _high_confidence_acceptance_plan(run)
        auto_count = len(plan["auto_accepted"])
        if auto_count > _AUTO_ACCEPT_WARNING_THRESHOLD:
            examples = "\n".join(
                f"  - {candidate.title}" for candidate in plan["auto_accepted"][:10]
            )
            _fail(
                "Refusing to auto-accept "
                f"{auto_count} high-confidence sources (threshold "
                f"{_AUTO_ACCEPT_WARNING_THRESHOLD}). Re-run with --yes to confirm.\n"
                f"First {min(auto_count, 10)} would-be accepted titles:\n{examples}"
            )

    register = _make_register_from_run(
        run,
        accept_high_confidence=accept_high_confidence,
        accept_ai_likely_accept=accept_ai_likely_accept,
    )
    save_source_register(register, output)


@app.command("expand-related-sources")
def expand_related_sources_cmd(
    source_register_json: Annotated[
        Path, typer.Argument(help="Path to SourceRegister JSON")
    ],
    category_json: Annotated[Path, typer.Argument(help="Path to category brief JSON")],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Write RelatedSourceExpansionRun JSON")
    ],
    limit_per_query: Annotated[
        int,
        typer.Option("--limit-per-query", min=1, help="Max Lex results per related query"),
    ] = 5,
    no_network: Annotated[
        bool,
        typer.Option("--no-network", help="Skip Lex network discovery"),
    ] = False,
    lex_base_url: Annotated[
        str | None,
        typer.Option("--lex-base-url", help="Lex API base URL override"),
    ] = None,
    lex_api_key: Annotated[
        str | None,
        typer.Option("--lex-api-key", help="Lex API key override"),
    ] = None,
    use_ai_triage: Annotated[
        bool,
        typer.Option("--use-ai-triage", help="Run AI relationship triage after classification"),
    ] = False,
    ai_triage_batch_size: Annotated[
        int,
        typer.Option("--ai-triage-batch-size", min=1, help="Relationships per AI triage batch"),
    ] = 15,
    model: Annotated[str | None, typer.Option("--model", help="AI model name override")] = None,
    litellm_base_url: Annotated[
        str | None,
        typer.Option("--litellm-base-url", help="LiteLLM base URL override"),
    ] = None,
    litellm_api_key: Annotated[
        str | None,
        typer.Option("--litellm-api-key", help="LiteLLM API key override"),
    ] = None,
    expansion_profile: Annotated[
        ExpansionProfile,
        typer.Option(
            "--expansion-profile",
            help="Query expansion scope: minimal, standard (default), or broad",
        ),
    ] = "standard",
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Exhaustive expansion (alias for --expansion-profile broad)",
        ),
    ] = False,
    max_seed_sources: Annotated[
        int | None,
        typer.Option(
            "--max-seed-sources",
            min=1,
            help="Limit seed sources used for expansion (after filtering)",
        ),
    ] = None,
    seed_source_type: Annotated[
        SeedSourceType,
        typer.Option(
            "--seed-source-type",
            help="Which accepted sources to use as expansion seeds (default: principal)",
        ),
    ] = "principal",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress progress output (still writes JSON)"),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option("--plain", help="Plain line-based progress without colours or bars"),
    ] = False,
) -> None:
    """Expand around accepted register sources to discover related legal materials."""
    if quiet and plain:
        _fail("Use either --quiet or --plain, not both.")

    mode = OutputMode.QUIET if quiet else (OutputMode.PLAIN if plain else OutputMode.RICH)
    ui = DiscoveryConsole(mode)

    if not source_register_json.exists():
        _fail(f"Source register file not found: {source_register_json}")
    try:
        register = load_source_register(source_register_json)
    except ValidationError as exc:
        _fail(f"Invalid SourceRegister JSON in {source_register_json}: {exc}")

    category = _load_category(category_json)
    if register.category_id != category.category_id:
        _fail(
            f"Source register category_id {register.category_id!r} "
            f"does not match category {category.category_id!r}"
        )

    use_network = not no_network
    resolved_profile: ExpansionProfile = "broad" if full else expansion_profile
    lex_adapter = None
    if use_network:
        lex_adapter = LexAdapter(base_url=lex_base_url, api_key=lex_api_key)
        lex_adapter.require_base_url()

    service = RelatedSourceExpansionService(lex_adapter=lex_adapter)
    try:
        run = service.run_related_source_expansion(
            category,
            register,
            limit_per_query=limit_per_query,
            use_network=use_network,
            use_ai_triage=use_ai_triage,
            ai_model_name=model,
            litellm_base_url=litellm_base_url,
            litellm_api_key=litellm_api_key,
            ai_triage_batch_size=ai_triage_batch_size,
            expansion_profile=resolved_profile,
            seed_source_type=seed_source_type,
            max_seed_sources=max_seed_sources,
            progress_callback=ui.handle_progress,
        )
    except AdaAIConfigurationError as exc:
        ui.fail(
            f"AI configuration is required when --use-ai-triage is set. Details: {exc}"
        )
    except LexAdapterError as exc:
        ui.fail(f"Lex related-source expansion failed: {exc}")

    save_related_source_expansion_run(run, output)
    ui.show_related_expansion_summary(run, output, use_ai_triage=use_ai_triage)
    ui.show_warnings_from_list(run.warnings)


RelatedSourceReviewStatus = Literal[
    "accepted",
    "parked",
    "rejected",
    "needs_more_research",
]


@app.command("review-related-source")
def review_related_source_cmd(
    related_run_json: Annotated[
        Path, typer.Argument(help="Path to RelatedSourceExpansionRun JSON")
    ],
    source_id: Annotated[str, typer.Argument(help="source_id of the related source to review")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Write updated RelatedSourceExpansionRun JSON"),
    ],
    status: Annotated[
        RelatedSourceReviewStatus,
        typer.Option("--status", help="Review status to apply"),
    ],
    relationship_to_category: Annotated[
        str | None,
        typer.Option(
            "--relationship-to-category",
            help="Optional relationship_to_category value",
        ),
    ] = None,
    notes: Annotated[
        str | None,
        typer.Option("--notes", help="Optional review notes"),
    ] = None,
) -> None:
    """Update review metadata for a related source in an expansion run."""
    if not related_run_json.exists():
        _fail(f"Related expansion run file not found: {related_run_json}")
    try:
        run = load_related_source_expansion_run(related_run_json)
    except ValidationError as exc:
        _fail(f"Invalid RelatedSourceExpansionRun JSON in {related_run_json}: {exc}")

    updated_sources: list[CandidateSource] = []
    found = False
    for source in run.related_sources:
        if source.source_id != source_id:
            updated_sources.append(source)
            continue
        found = True
        updates: dict[str, object] = {"review_status": status}
        if relationship_to_category is not None:
            updates["relationship_to_category"] = relationship_to_category
        if notes is not None:
            updates["notes"] = notes
        updated_sources.append(source.model_copy(update=updates))

    if not found:
        _fail(f"Related source {source_id!r} not found in {related_run_json}")

    updated_run = run.model_copy(update={"related_sources": updated_sources})
    save_related_source_expansion_run(updated_run, output)
    typer.echo(f"Updated related source {source_id!r} in {output}")


@app.command("make-source-bundle")
def make_source_bundle_cmd(
    source_register_json: Annotated[
        Path, typer.Argument(help="Path to SourceRegister JSON")
    ],
    output: Annotated[Path, typer.Option("--output", "-o", help="Write SourceBundle JSON")],
    related_run: Annotated[
        Path | None,
        typer.Option("--related-run", help="Optional RelatedSourceExpansionRun JSON"),
    ] = None,
) -> None:
    """Build a structured source bundle from a register and optional related expansion."""
    if not source_register_json.exists():
        _fail(f"Source register file not found: {source_register_json}")
    try:
        register = load_source_register(source_register_json)
    except ValidationError as exc:
        _fail(f"Invalid SourceRegister JSON in {source_register_json}: {exc}")

    expansion_run = None
    if related_run is not None:
        if not related_run.exists():
            _fail(f"Related expansion run file not found: {related_run}")
        try:
            expansion_run = load_related_source_expansion_run(related_run)
        except ValidationError as exc:
            _fail(f"Invalid RelatedSourceExpansionRun JSON in {related_run}: {exc}")
        if expansion_run.category_id != register.category_id:
            _fail(
                f"Related run category_id {expansion_run.category_id!r} "
                f"does not match register {register.category_id!r}"
            )

    bundle = build_source_bundle(register.category_id, register, expansion_run)
    save_source_bundle(bundle, output)
    typer.echo(f"Wrote source bundle to {output}")
    typer.echo(f"Principal sources: {len(bundle.principal_sources)}")
    typer.echo(f"Relationships: {len(bundle.relationships)}")


@app.command("make-law-proposition-extractor-intake-bundle")
@app.command("make-law-proposition-extractor-intake-bundle", hidden=True)  # COMPAT_LEGACY_NAME remove in rename+1
def make_law_proposition_extractor_intake_bundle_cmd(
    source_bundle_json: Annotated[
        Path,
        typer.Argument(help="Path to reviewed SourceBundle JSON"),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Write Law Proposition Extractor intake SourceBundle JSON"),
    ],
    principal_only: Annotated[
        bool,
        typer.Option(
            "--principal-only",
            help="Include only accepted principal sources; omit amending, revocation, and relationships.",
        ),
    ] = False,
    max_principal_sources: Annotated[
        int | None,
        typer.Option(
            "--max-principal-sources",
            min=1,
            help="Limit accepted principal sources (useful for Law Proposition Extractor smoke tests).",
        ),
    ] = None,
    exclude_jurisdiction: Annotated[
        list[str],
        typer.Option(
            "--exclude-jurisdiction",
            help=(
                'Exclude sources whose title contains this jurisdiction (e.g. "Northern Ireland") '
                "or match jurisdiction-specific legislation URI patterns such as /nisr/."
            ),
        ),
    ] = [],
    priority_policy: Annotated[
        Literal["raw", "current_core"],
        typer.Option(
            "--priority-policy",
            help=(
                "Principal source ordering before --max-principal-sources: "
                "raw keeps input order; current_core prioritises current slurry instruments."
            ),
        ),
    ] = "raw",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print summary without writing output."),
    ] = False,
) -> None:
    """Create a slim Law Proposition Extractor intake bundle from a reviewed Law Discovery source bundle.

    Law Discovery source bundles preserve contextual, rejected, parked, and needs_more_research
    material for audit and review. Law Proposition Extractor first-pass intake should usually include only
    accepted principal, amending, and revocation sources plus accepted relationships.

    The reviewed Law Discovery bundle remains the audit artefact; the Law Proposition Extractor intake bundle is a
    filtered consumption artefact that reduces extraction work and LLM token cost.
    """
    if not source_bundle_json.exists():
        _fail(f"Source bundle file not found: {source_bundle_json}")
    try:
        bundle = load_source_bundle(source_bundle_json)
    except ValidationError as exc:
        _fail(f"Invalid SourceBundle JSON in {source_bundle_json}: {exc}")

    result = make_law_proposition_extractor_intake_bundle(
        bundle,
        principal_only=principal_only,
        max_principal_sources=max_principal_sources,
        exclude_jurisdictions=set(exclude_jurisdiction),
        priority_policy=priority_policy,
    )

    try:
        SourceBundle.model_validate(result.bundle.model_dump())
    except ValidationError as exc:
        _fail(f"Generated Law Proposition Extractor intake bundle failed validation: {exc}")

    summary = format_law_proposition_extractor_intake_summary(
        result,
        output_path=str(output),
        dry_run=dry_run,
    )
    typer.echo(summary)

    if not dry_run:
        save_source_bundle(result.bundle, output)


@app.command("export-for-law-proposition-extractor")
def export_for_judit_cmd(
    source_register_json: Annotated[Path, typer.Argument(help="Path to SourceRegister JSON")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Write Law Proposition Extractor handoff JSON"),
    ],
) -> None:
    """Export accepted sources from a register for Law Proposition Extractor."""
    if not source_register_json.exists():
        _fail(f"Source register file not found: {source_register_json}")
    register: SourceRegister
    try:
        register = load_source_register(source_register_json)
    except ValidationError as exc:
        _fail(f"Invalid SourceRegister JSON in {source_register_json}: {exc}")

    save_selected_sources_for_judit(register, output)


@app.command("export-bundle-for-law-proposition-extractor")
def export_bundle_for_judit_cmd(
    source_bundle_json: Annotated[Path, typer.Argument(help="Path to SourceBundle JSON")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Write Law Proposition Extractor source bundle handoff JSON"),
    ],
) -> None:
    """Export a source bundle for richer Law Proposition Extractor handoff (relationships included)."""
    if not source_bundle_json.exists():
        _fail(f"Source bundle file not found: {source_bundle_json}")
    try:
        bundle = load_source_bundle(source_bundle_json)
    except ValidationError as exc:
        _fail(f"Invalid SourceBundle JSON in {source_bundle_json}: {exc}")

    save_source_bundle_for_judit(bundle, output)
    typer.echo(f"Wrote Law Proposition Extractor bundle export to {output}")


def main() -> None:
    load_dotenv()
    try:
        app()
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - last-resort CLI guard
        _fail(f"Unexpected error: {exc}")


if __name__ == "__main__":
    main()
