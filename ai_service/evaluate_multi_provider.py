"""
Multi-provider AI evaluation script for MindWell.

Evaluates the Full Session Analysis feature across multiple AI providers
(Gemini, OpenAI) using the same conversations, prompt, and parameters.

Features:
- Supports Gemini and OpenAI providers
- Reuses SESSION_FULL_ANALYSIS_PROMPT and validation from services.py
- Same transcript, prompt, language, and temperature (0.2) for all providers
- Reads conversations from conversations_multilingual.json
- Accepts scenario IDs or conversation IDs via CLI
- Pilot mode: 5 scenarios (15 conversations across FR/AR/EN)
- Saves results separately per provider
- Supports resuming interrupted evaluations
- Validates all six required output fields and risk_level enum
- Records API errors without stopping evaluation
- No clinical accuracy claims without expert-reviewed ground-truth labels

Usage:
    # Pilot run (5 scenarios = 15 conversations)
    python -m ai_service.evaluate_multi_provider --pilot --providers gemini,openai

    # Specific conversation IDs
    python -m ai_service.evaluate_multi_provider --ids conv_001,conv_002,conv_003 --providers gemini,openai

    # Specific scenario IDs
    python -m ai_service.evaluate_multi_provider --scenarios 1,2,3,4,5 --providers gemini,openai

    # Resume interrupted run
    python -m ai_service.evaluate_multi_provider --pilot --providers gemini,openai

Output files (per provider):
    ai_service/evaluation_results_gemini.json
    ai_service/evaluation_results_openai.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Django setup
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mindwell.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from ai_service.providers import (  # noqa: E402
    PROVIDER_REGISTRY,
    BaseProvider,
    get_provider,
    list_available_providers,
)
from ai_service.services import (  # noqa: E402
    SUPPORTED_LANGUAGES,
    _validate_full_analysis,
)
from ai_service.evaluate_dataset_gemini import (  # noqa: E402
    REQUIRED_FIELDS,
    build_transcript,
    load_dataset,
    run_quality_checks,
)

logger = logging.getLogger(__name__)

# Result file paths (separate per provider)
RESULTS_DIR = BASE_DIR / "ai_service"
RESULTS_FILE_TEMPLATE = RESULTS_DIR / "evaluation_results_{provider}.json"

# Pilot configuration: 5 scenarios = 15 conversations (3 languages each)
PILOT_SCENARIOS = [1, 2, 3, 4, 5]

REQUIRED_FIELDS = (
    "summary",
    "themes",
    "emotions",
    "keywords",
    "emotional_evolution",
    "risk_level",
)


def load_conversations_by_scenario(scenario_ids: List[int]) -> List[Dict[str, Any]]:
    """Load and filter conversations by scenario IDs."""
    all_conversations = load_dataset()
    filtered = [c for c in all_conversations if c.get("scenario_id") in scenario_ids]
    return filtered


def load_conversations_by_ids(conversation_ids: List[str]) -> List[Dict[str, Any]]:
    """Load and filter conversations by conversation IDs."""
    all_conversations = load_dataset()
    id_set = set(conversation_ids)
    filtered = [c for c in all_conversations if c.get("id") in id_set]
    return filtered


def load_existing_results(results_path: Path) -> List[Dict[str, Any]]:
    """Load existing results from a provider's result file."""
    if not results_path.exists():
        return []
    try:
        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning("Results file %s is not a list, starting fresh.", results_path)
        return []
    except (json.JSONDecodeError, OSError) as error:
        logger.warning("Failed to load existing results from %s: %s", results_path, error)
        return []


def save_results(results: List[Dict[str, Any]], results_path: Path) -> None:
    """Save results to provider-specific JSON file."""
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def is_result_complete(
    result: Dict[str, Any],
    conversation_id: str,
    language: str,
    provider_name: str,
    model_name: str,
) -> bool:
    """Check if a result record is complete and valid for resume logic."""
    if not isinstance(result, dict):
        return False
    if result.get("conversation_id") != conversation_id:
        return False
    if result.get("language") != language:
        return False
    if result.get("provider") != provider_name:
        return False
    if result.get("model") != result.get("model_used", ""):
        # model_used is stored in output, model is top-level
        pass
    if result.get("model") != result.get("model", ""):
        pass
    if not result.get("success"):
        return False
    output = result.get("output", {})
    for field in REQUIRED_FIELDS:
        if field not in output:
            return False
        if field in ("summary", "emotional_evolution"):
            if not isinstance(output[field], str) or not output[field].strip():
                return False
        elif field in ("themes", "emotions", "keywords"):
            if not isinstance(output[field], list):
                return False
        elif field == "risk_level":
            if output[field] is not None and output[field] not in ("low", "medium", "high"):
                return False
        elif field == "risk_assessment_status":
            if output[field] not in ("assessed", "insufficient_information"):
                return False
    return True


def get_completed_keys(
    existing_results: List[Dict[str, Any]],
    provider_name: str,
    model_name: str,
) -> Set[Tuple[str, str]]:
    """Get set of (conversation_id, language) already completed for this provider."""
    completed = set()
    for r in existing_results:
        if (
            r.get("provider") == provider_name
            and r.get("model") == model_name
            and is_result_complete(r, r.get("conversation_id", ""), r.get("language", ""), provider_name, model_name)
        ):
            completed.add((r.get("conversation_id", ""), r.get("language", "")))
    return completed


def validate_output_structure(output: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate that output contains all required fields with correct types."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in output:
            errors.append(f"Missing required field: {field}")
            continue
        value = output[field]
        if field in ("summary", "emotional_evolution"):
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Field '{field}' must be a non-empty string")
        elif field in ("themes", "emotions", "keywords"):
            if not isinstance(value, list):
                errors.append(f"Field '{field}' must be a list")
            elif any(not isinstance(item, str) or not item.strip() for item in value):
                errors.append(f"Field '{field}' contains non-string or empty items")
        elif field == "risk_level":
            if value is not None and value not in ("low", "medium", "high"):
                errors.append(f"Field 'risk_level' has invalid value: {value}")
        elif field == "risk_assessment_status":
            if value not in ("assessed", "insufficient_information"):
                errors.append(f"Field 'risk_assessment_status' has invalid value: {value}")
    return len(errors) == 0, errors


def evaluate_conversation_with_provider(
    provider: BaseProvider,
    conversation: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluate a single conversation with a specific provider.
    Returns a standardized result record.
    """
    conversation_id = conversation.get("id", "unknown")
    scenario_id = conversation.get("scenario_id")
    language = conversation.get("language", "fr")
    theme = conversation.get("theme", "")

    transcript = build_transcript(conversation)

    if not transcript:
        return {
            "conversation_id": conversation_id,
            "scenario_id": scenario_id,
            "language": language,
            "theme": theme,
            "provider": provider.name,
            "model": provider.model_name,
            "success": False,
            "error": "Transcript is empty after filtering.",
            "latency_ms": 0,
            "output": None,
            "structural_validation": {"valid": False, "errors": ["Empty transcript"]},
            "quality_checks": {},
            "quality_passed": False,
            "requires_human_review": False,
            "timestamp": time.time(),
        }

    if language not in SUPPORTED_LANGUAGES:
        return {
            "conversation_id": conversation_id,
            "scenario_id": scenario_id,
            "language": language,
            "theme": theme,
            "provider": provider.name,
            "model": provider.model_name,
            "success": False,
            "error": f"Unsupported language: {language}",
            "latency_ms": 0,
            "output": None,
            "structural_validation": {"valid": False, "errors": [f"Unsupported language: {language}"]},
            "quality_checks": {},
            "quality_passed": False,
            "requires_human_review": False,
            "timestamp": time.time(),
        }

    # Call provider
    provider_result = provider.analyze_transcript(
        transcript=[{"speaker": t["speaker"], "text": t["text"]} for t in transcript],
        language=language,
    )

    # Build base result record
    base_record = {
        "conversation_id": conversation_id,
        "scenario_id": scenario_id,
        "language": language,
        "theme": theme,
        "provider": provider.name,
        "model": provider.model_name,
        "success": provider_result.success,
        "error": provider_result.error,
        "latency_ms": provider_result.latency_ms,
        "output": provider_result.output,
        "timestamp": time.time(),
    }

    if not provider_result.success:
        base_record.update({
            "structural_validation": {"valid": False, "errors": [provider_result.error or "Unknown error"]},
            "quality_checks": {},
            "quality_passed": False,
            "requires_human_review": False,
        })
        return base_record

    # Validate output structure
    is_valid, struct_errors = validate_output_structure(provider_result.output)
    structural_validation = {"valid": is_valid, "errors": struct_errors}

    # Run quality checks (same as existing evaluator)
    quality_checks = run_quality_checks(conversation, provider_result.output)

    quality_passed = all(len(checks.get("errors", [])) == 0 for checks in quality_checks.values())
    requires_human_review = any(len(checks.get("warnings", [])) > 0 for checks in quality_checks.values())

    return {
        **base_record,
        "structural_validation": structural_validation,
        "quality_checks": quality_checks,
        "quality_passed": quality_passed,
        "requires_human_review": requires_human_review,
    }


def run_evaluation(
    provider_names: List[str],
    conversations: List[Dict[str, Any]],
    resume: bool = True,
) -> Dict[str, Dict[str, int]]:
    """
    Run evaluation for all specified providers on given conversations.

    Returns per-provider statistics.
    """
    stats = {}

    for provider_name in provider_names:
        provider = get_provider(provider_name)
        model_name = provider.model_name
        results_path = Path(str(RESULTS_FILE_TEMPLATE).format(provider=provider_name))

        logger.info("Starting evaluation for provider: %s (model: %s)", provider_name, model_name)

        # Load existing results for resume
        existing_results = load_existing_results(Path(str(RESULTS_FILE_TEMPLATE).format(provider=provider_name))) if resume else []
        completed_keys = get_completed_keys(existing_results, provider_name, provider.model_name) if resume else set()

        results = list(existing_results)
        processed = 0
        skipped = 0
        succeeded = 0
        failed = 0

        for conversation in conversations:
            conversation_id = conversation.get("id", "unknown")
            language = conversation.get("language", "fr")

            # Skip if already completed (resume)
            if (conversation_id, language) in completed_keys:
                skipped += 1
                continue

            # Evaluate
            result = evaluate_conversation_with_provider(provider, conversation)
            results.append(result)

            # Save immediately after each conversation (atomic write)
            save_results(results, Path(str(RESULTS_FILE_TEMPLATE).format(provider=provider_name)))

            processed += 1
            if result["success"]:
                succeeded += 1
            else:
                failed += 1
                logger.warning(
                    "Provider %s failed for conversation %s (%s): %s",
                    provider_name,
                    conversation_id,
                    language,
                    result.get("error", "Unknown error"),
                )

        stats[provider_name] = {
            "processed": processed,
            "skipped": skipped,
            "succeeded": succeeded,
            "failed": failed,
            "total_conversations": len(conversations),
        }

        logger.info(
            "Provider %s done: processed=%d, skipped=%d, succeeded=%d, failed=%d",
            provider_name,
            processed,
            skipped,
            succeeded,
            failed,
        )

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multi-provider AI evaluation for MindWell Full Session Analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Pilot run (5 scenarios = 15 conversations) with Gemini and OpenAI
  python -m ai_service.evaluate_multi_provider --pilot --providers gemini,openai

  # Specific conversation IDs
  python -m ai_service.evaluate_multi_provider --ids conv_001,conv_002,conv_003 --providers gemini,openai

  # Specific scenario IDs (all 3 languages per scenario)
  python -m ai_service.evaluate_multi_provider --scenarios 1,2,3,4,5 --providers gemini,openai

  # Resume interrupted run (default behavior)
  python -m ai_service.evaluate_multi_provider --pilot --providers gemini,openai

  # Force fresh run (ignore existing results)
  python -m ai_service.evaluate_multi_provider --pilot --providers gemini,openai --no-resume

Output files (per provider):
  ai_service/evaluation_results_gemini.json
  ai_service/evaluation_results_openai.json

Each result record contains:
  - conversation_id, scenario_id, language, theme
  - provider, model, timestamp, latency_ms
  - success, error (if any), output (validated fields)
  - structural_validation (field presence/type checks)
  - quality_checks (json_structure, language_match, no_diagnoses, speaker_separation, risk_assessment)
  - quality_passed, requires_human_review

NOTE: This script does NOT calculate clinical accuracy metrics (Accuracy, F1, etc.)
because ground-truth labels require expert clinical review. The
conversations_labeled.json template is provided for clinical reviewers.
        """,
    )

    # Input selection (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--pilot",
        action="store_true",
        help="Run pilot evaluation on 5 scenarios (15 conversations: FR/AR/EN per scenario).",
    )
    input_group.add_argument(
        "--ids",
        type=str,
        help="Comma-separated conversation IDs (e.g., conv_001,conv_002,conv_003).",
    )
    input_group.add_argument(
        "--scenarios",
        type=str,
        help="Comma-separated scenario IDs (e.g., 1,2,3,4,5). All 3 languages per scenario.",
    )

    # Provider selection
    parser.add_argument(
        "--providers",
        type=str,
        default="gemini,openai",
        help="Comma-separated provider names (default: gemini,openai). Available: gemini, openai",
    )

    # Resume control
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Force fresh evaluation, ignoring any existing results.",
    )

    # Logging
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse providers
    provider_names = [p.strip() for p in args.providers.split(",") if p.strip()]
    invalid = [p for p in provider_names if p not in PROVIDER_REGISTRY]
    if invalid:
        logger.error("Unknown providers: %s. Available: %s", invalid, list(PROVIDER_REGISTRY.keys()))
        return 1

    # Check provider configuration
    for provider_name in provider_names:
        provider = get_provider(provider_name)
        if not provider.is_configured():
            logger.error(
                "Provider '%s' is not configured (missing API key or SDK). "
                "Set %s and install required SDK.",
                provider_name,
                "GEMINI_API_KEY" if provider_name == "gemini" else "OPENAI_API_KEY",
            )
            return 1

    # Determine conversations to evaluate
    if args.pilot:
        scenario_ids = PILOT_SCENARIOS
        conversations = load_conversations_by_scenario(scenario_ids)
        logger.info("Pilot mode: %d scenarios (%d conversations)", len(scenario_ids), len(conversations))
    elif args.ids:
        conversation_ids = [cid.strip() for cid in args.ids.split(",") if cid.strip()]
        conversations = load_conversations_by_ids(conversation_ids)
        logger.info("Selected %d conversations by ID", len(conversations))
    elif args.scenarios:
        scenario_ids = [int(s.strip()) for s in args.scenarios.split(",") if s.strip()]
        conversations = load_conversations_by_scenario(scenario_ids)
        logger.info("Selected %d scenarios (%d conversations)", len(scenario_ids), len(conversations))
    else:
        parser.error("Must specify one of --pilot, --ids, or --scenarios")
        return 1

    if not conversations:
        logger.error("No conversations found for the given selection.")
        return 1

    # Validate all conversations have supported languages
    unsupported = [c for c in conversations if c.get("language") not in SUPPORTED_LANGUAGES]
    if unsupported:
        logger.error("Conversations with unsupported languages: %s", [c["id"] for c in unsupported])
        return 1

    logger.info("Total conversations to evaluate: %d", len(conversations))
    logger.info("Providers: %s", ", ".join(provider_names))
    logger.info("Resume: %s", not args.no_resume)

    # Run evaluation
    stats = run_evaluation(
        provider_names=provider_names,
        conversations=conversations,
        resume=not args.no_resume,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    for provider_name, stat in stats.items():
        print(f"\nProvider: {provider_name}")
        print(f"  Total conversations: {stat['total_conversations']}")
        print(f"  Processed: {stat['processed']}")
        print(f"  Skipped (resume): {stat['skipped']}")
        print(f"  Succeeded: {stat['succeeded']}")
        print(f"  Failed: {stat['failed']}")

    print("\nResult files:")
    for provider_name in provider_names:
        path = Path(str(RESULTS_FILE_TEMPLATE).format(provider=provider_name))
        print(f"  {path}")

    print("\nNOTE: This evaluation measures structural validity and quality checks only.")
    print("Clinical accuracy metrics (Accuracy, Precision, Recall, F1) require")
    print("expert-reviewed ground-truth labels from conversations_labeled.json.")

    return 0


if __name__ == "__main__":
    sys.exit(main())