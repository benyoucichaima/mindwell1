"""
Custom evaluation script for synthetic datasets using Groq provider.
Evaluates:
- conversations_risk_test.json (14 conversations: FR/EN/AR)
- conversations_arabic_darija_test.json (10 conversations: AR/Darija)
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List

# Load .env
BASE_DIR = Path(__file__).resolve().parent.parent
with open(BASE_DIR / ".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k] = v

sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mindwell.settings")

import django
django.setup()

from django.conf import settings
from ai_service.providers import get_provider, GroqProvider
from ai_service.evaluate_dataset_gemini import (
    REQUIRED_FIELDS,
    build_transcript,
    run_quality_checks,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATASETS = [
    "ai_service/datasets/conversations_risk_test.json",
    "ai_service/datasets/conversations_arabic_darija_test.json",
]

RESULTS_FILE = BASE_DIR / "ai_service" / "evaluation_results_groq_synthetic.json"


def load_dataset(path: str) -> List[Dict[str, Any]]:
    full_path = BASE_DIR / path
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_existing_results() -> List[Dict[str, Any]]:
    if not RESULTS_FILE.exists():
        return []
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_results(results: List[Dict[str, Any]]) -> None:
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def is_complete(result: Dict[str, Any], conv_id: str, lang: str) -> bool:
    if not result.get("success"):
        return False
    if result.get("conversation_id") != conv_id:
        return False
    if result.get("language") != lang:
        return False
    output = result.get("output", {})
    for field in REQUIRED_FIELDS:
        if field not in output:
            return False
    return True


def evaluate_conversation(provider, conversation: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """Evaluate a single conversation with the provider."""
    conv_id = conversation["id"]
    language = conversation["language"]
    messages = conversation["messages"]

    # Build transcript for provider (patient + psychologist)
    transcript = [
        {"speaker": m["speaker"], "text": m["content"]}
        for m in messages
    ]

    logger.info(f"Evaluating {conv_id} ({language})...")
    
    # Retry logic for rate limits
    max_retries = 3
    for attempt in range(max_retries):
        result = provider.analyze_transcript(transcript, language)
        
        if result.success:
            break
            
        # Check if it's a rate limit error (HTTP 429)
        if "429" in str(result.error) or "Rate limit" in str(result.error):
            wait_time = (attempt + 1) * 10  # 10s, 20s, 30s
            logger.warning(f"  Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)
            continue
        else:
            # Non-rate-limit error, don't retry
            break
    else:
        # All retries exhausted
        logger.error(f"  Failed after {max_retries} retries")

    # Build output record
    record = {
        "conversation_id": conv_id,
        "language": language,
        "provider": provider.name,
        "model": model_name,
        "success": result.success,
        "latency_ms": result.latency_ms,
    }

    if result.success:
        output = result.output
        record["output"] = output

        # Run quality checks including risk consistency
        quality = run_quality_checks(
            conversation=conversation,
            result=output,
        )
        record["quality_checks"] = quality
    else:
        record["error"] = result.error
        record["quality_checks"] = {"errors": [result.error] if result.error else [], "warnings": []}

    return record


def main():
    # Initialize Groq provider
    provider = GroqProvider()
    if not provider.is_configured():
        logger.error("Groq provider not configured (GROQ_API_KEY missing)")
        sys.exit(1)

    model_name = provider.model_name
    logger.info(f"Using provider: {provider.name}, model: {model_name}")

    # Load existing results for resume
    existing = load_existing_results()
    completed = set()
    for r in existing:
        if is_complete(r, r.get("conversation_id", ""), r.get("language", "")):
            completed.add((r["conversation_id"], r["language"]))

    logger.info(f"Found {len(completed)} completed evaluations to resume")

    # Load all conversations from both datasets
    all_conversations = []
    for ds_path in DATASETS:
        convs = load_dataset(ds_path)
        all_conversations.extend(convs)
        logger.info(f"Loaded {len(convs)} conversations from {ds_path}")

    logger.info(f"Total conversations: {len(all_conversations)}")

    # Filter out completed
    to_evaluate = [c for c in all_conversations if (c["id"], c["language"]) not in completed]
    logger.info(f"Conversations to evaluate: {len(to_evaluate)}")

    if not to_evaluate:
        logger.info("All conversations already evaluated!")
        return

    # Evaluate each conversation
    results = list(existing)
    for i, conv in enumerate(to_evaluate, 1):
        logger.info(f"[{i}/{len(to_evaluate)}] {conv['id']} ({conv['language']})")
        record = evaluate_conversation(provider, conv, model_name)
        results.append(record)

        # Save after each conversation
        save_results(results)
        logger.info(f"  Success: {record['success']}, Latency: {record['latency_ms']}ms")
        if record['success']:
            qc = record['quality_checks']
            logger.info(f"  Warnings: {len(qc.get('warnings', []))}, Errors: {len(qc.get('errors', []))}")

    # Final report
    logger.info("=" * 60)
    logger.info("EVALUATION COMPLETE")
    logger.info("=" * 60)

    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count
    total_latency = sum(r.get("latency_ms", 0) for r in results if r.get("success"))
    avg_latency = total_latency / success_count if success_count else 0

    logger.info(f"Total: {len(results)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {fail_count}")
    logger.info(f"Avg latency: {avg_latency:.0f}ms")

    # Language breakdown
    by_lang = {}
    for r in results:
        lang = r.get("language", "unknown")
        if lang not in by_lang:
            by_lang[lang] = {"total": 0, "success": 0, "fail": 0, "warnings": 0, "errors": 0}
        by_lang[lang]["total"] += 1
        if r.get("success"):
            by_lang[lang]["success"] += 1
            by_lang[lang]["warnings"] += len(r.get("quality_checks", {}).get("warnings", []))
            by_lang[lang]["errors"] += len(r.get("quality_checks", {}).get("errors", []))
        else:
            by_lang[lang]["fail"] += 1

    logger.info("\nBy Language:")
    for lang, stats in sorted(by_lang.items()):
        logger.info(f"  {lang}: {stats['success']}/{stats['total']} success, "
                   f"{stats['warnings']} warnings, {stats['errors']} errors")

    # Risk consistency warnings
    risk_warnings = []
    for r in results:
        if r.get("success"):
            for w in r.get("quality_checks", {}).get("warnings", []):
                if "risk_level" in w.lower() or "urgent" in w.lower():
                    risk_warnings.append(f"{r['conversation_id']} ({r['language']}): {w}")

    if risk_warnings:
        logger.info(f"\nRisk Consistency Warnings ({len(risk_warnings)}):")
        for w in risk_warnings:
            logger.info(f"  {w}")
    else:
        logger.info("\nNo risk consistency warnings.")

    # Language preservation check
    lang_issues = []
    for r in results:
        if r.get("success"):
            output = r.get("output", {})
            summary = output.get("summary", "")
            if summary:
                # Simple check: French summary should contain French words, Arabic should contain Arabic
                lang = r.get("language")
                if lang == "fr":
                    # Check for French-specific words
                    pass
                elif lang == "ar":
                    # Check for Arabic script
                    has_arabic = any('\u0600' <= c <= '\u06FF' for c in summary)
                    if not has_arabic and summary.strip():
                        lang_issues.append(f"{r['conversation_id']}: Arabic response missing Arabic script")

    if lang_issues:
        logger.info(f"\nLanguage Preservation Issues ({len(lang_issues)}):")
        for issue in lang_issues:
            logger.info(f"  {issue}")
    else:
        logger.info("\nLanguage preservation: OK")

    logger.info(f"\nResults saved to: {RESULTS_FILE}")


if __name__ == "__main__":
    main()