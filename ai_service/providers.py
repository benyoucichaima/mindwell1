"""
Provider abstraction for multi-provider AI evaluation.

This module provides a common interface for different AI providers (Gemini, OpenAI, Cohere, Groq)
to be used in evaluation scripts WITHOUT modifying the live application's
provider routing in services.py.
"""

import json
import time
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from django.conf import settings

from ai_service.services import (
    SESSION_FULL_ANALYSIS_PROMPT,
    SUPPORTED_LANGUAGES,
    _validate_full_analysis,
    _ai_error_message,
    _gemini_error_message,
)

logger = logging.getLogger(__name__)


# Temperature is fixed at 0.2 for both providers to ensure fair comparison
EVALUATION_TEMPERATURE = 0.2


def build_effective_prompt(language: str) -> str:
    """
    Build the effective prompt with explicit language instruction for evaluation.

    This wrapper adds a clear language directive to the base SESSION_FULL_ANALYSIS_PROMPT
    without modifying the original prompt. Used only by evaluation providers.
    """
    language_instructions = {
        "fr": "Respond exclusively in French.",
        "ar": "Respond in Arabic, preserving the patient's language style (Algerian Darija or Modern Standard Arabic).",
        "en": "Respond exclusively in English.",
    }
    instruction = language_instructions.get(language, language_instructions["fr"])
    return f"{instruction}\n\n{SESSION_FULL_ANALYSIS_PROMPT}"


@dataclass
class ProviderResult:
    """Standardized result from a provider analysis call."""
    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: int = 0


class BaseProvider(ABC):
    """Abstract base class for AI providers in evaluation context."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'gemini', 'openai')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name used by this provider."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider has required API keys and SDK."""
        pass

    @abstractmethod
    def analyze_transcript(self, transcript: List[Dict[str, str]], language: str) -> ProviderResult:
        """
        Analyze a transcript using this provider.

        Args:
            transcript: List of {"speaker": str, "text": str}
            language: One of "ar", "fr", "en"

        Returns:
            ProviderResult with success flag, output dict, error message, and latency.
        """
        pass


class GeminiProvider(BaseProvider):
    """Google Gemini provider using the existing _ask_gemini function logic."""

    def __init__(self):
        # Use gemini-3.5-flash for evaluation (per user request); live app uses GEMINI_MODEL from settings
        self._model_name = "gemini-3.5-flash"

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    def is_configured(self) -> bool:
        try:
            from google import genai
        except ImportError:
            return False
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        return bool(api_key)

    def _is_transient_error(self, error: Exception) -> bool:
        """Check if an error is transient and should be retried."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        # Google GenAI SDK specific exceptions
        if "permissiondenied" in error_type or "unauthenticated" in error_type:
            return False
        if "notfound" in error_type or "invalidargument" in error_type:
            return False
        if "resourceexhausted" in error_type or "quota" in error_str:
            return False

        # HTTP status codes that indicate transient errors
        if hasattr(error, "code"):
            if error.code in (503, 502, 504):
                return True
            if error.code in (401, 403, 404):
                return False

        # Check error message for transient indicators
        transient_indicators = [
            "service unavailable",
            "temporarily unavailable",
            "internal error",
            "deadline exceeded",
            "timeout",
            "connection",
            "503",
            "502",
            "504",
        ]
        for indicator in transient_indicators:
            if indicator in error_str:
                return True

        permanent_indicators = [
            "invalid api key",
            "unauthorized",
            "forbidden",
            "not found",
            "invalid model",
            "permission denied",
            "authentication",
        ]
        for indicator in permanent_indicators:
            if indicator in error_str:
                return False

        return False

    def analyze_transcript(self, transcript: List[Dict[str, str]], language: str) -> ProviderResult:
        start_time = time.perf_counter()

        if language not in SUPPORTED_LANGUAGES:
            return ProviderResult(
                success=False,
                error=f"Unsupported language: {language}",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )
        if not transcript or not isinstance(transcript, list):
            return ProviderResult(
                success=False,
                error="Transcript is empty or invalid.",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        effective_prompt = build_effective_prompt(language)

        max_attempts = 3
        backoff_seconds = [1, 2]  # 1s then 2s between attempts

        last_error = None

        for attempt in range(max_attempts):
            try:
                # Import here to avoid SDK dependency at module load
                from google import genai

                client = genai.Client(api_key=getattr(settings, "GEMINI_API_KEY", ""))
                if not client:
                    raise RuntimeError(_gemini_error_message())

                response = client.models.generate_content(
                    model=self._model_name,
                    contents=json.dumps(transcript, ensure_ascii=False),
                    config={
                        "system_instruction": effective_prompt,
                        "response_mime_type": "application/json",
                        "temperature": EVALUATION_TEMPERATURE,
                    },
                )
                data = json.loads(response.text)

            except json.JSONDecodeError:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                return ProviderResult(
                    success=False,
                    error="The AI provider returned invalid output (invalid JSON).",
                    latency_ms=latency_ms,
                )
            except Exception as error:
                last_error = error
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                # Check if we should retry
                if attempt < max_attempts - 1 and self._is_transient_error(error):
                    wait_time = backoff_seconds[attempt]
                    logger.warning(
                        "Gemini analysis attempt %d/%d failed with transient error, retrying in %ds: type=%s, message=%s",
                        attempt + 1,
                        max_attempts,
                        wait_time,
                        type(error).__name__,
                        str(error),
                    )
                    time.sleep(wait_time)
                    continue

                # Non-transient error or max attempts reached
                error_message = _gemini_error_message(error)
                logger.warning(
                    "Gemini analysis failed after %d attempt(s): type=%s, message=%s",
                    attempt + 1,
                    type(error).__name__,
                    str(error),
                )
                return ProviderResult(
                    success=False,
                    error=error_message,
                    latency_ms=latency_ms,
                )

            # Success - break out of retry loop
            break

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        validated = _validate_full_analysis(data)
        if validated is None:
            return ProviderResult(
                success=False,
                error="The AI provider returned invalid output.",
                latency_ms=latency_ms,
            )

        return ProviderResult(success=True, output=validated, latency_ms=latency_ms)


class OpenAIProvider(BaseProvider):
    """OpenAI provider using the existing _ask function logic."""

    def __init__(self):
        self._model_name = getattr(settings, "AI_MODEL", "gpt-4o-mini")

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    def is_configured(self) -> bool:
        try:
            from openai import OpenAI
        except ImportError:
            return False
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        return bool(api_key)

    def analyze_transcript(self, transcript: List[Dict[str, str]], language: str) -> ProviderResult:
        start_time = time.perf_counter()

        if language not in SUPPORTED_LANGUAGES:
            return ProviderResult(
                success=False,
                error=f"Unsupported language: {language}",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )
        if not transcript or not isinstance(transcript, list):
            return ProviderResult(
                success=False,
                error="Transcript is empty or invalid.",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        effective_prompt = build_effective_prompt(language)

        try:
            from openai import OpenAI

            client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", ""))
            if not client:
                raise RuntimeError(_ai_error_message())

            response = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": effective_prompt},
                    {"role": "user", "content": json.dumps(transcript, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=EVALUATION_TEMPERATURE,
            )
            data = json.loads(response.choices[0].message.content)

        except json.JSONDecodeError:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return ProviderResult(
                success=False,
                error="The AI provider returned invalid output (invalid JSON).",
                latency_ms=latency_ms,
            )
        except Exception as error:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_message = _ai_error_message(error)
            logger.warning(
                "OpenAI analysis failed: type=%s, message=%s",
                type(error).__name__,
                str(error),
            )
            return ProviderResult(
                success=False,
                error=error_message,
                latency_ms=latency_ms,
            )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        validated = _validate_full_analysis(data)
        if validated is None:
            return ProviderResult(
                success=False,
                error="The AI provider returned invalid output.",
                latency_ms=latency_ms,
            )

        return ProviderResult(success=True, output=validated, latency_ms=latency_ms)


class CohereProvider(BaseProvider):
    """Cohere provider using REST API (v1 chat endpoint)."""

    def __init__(self):
        self._model_name = "command-r-08-2024"

    @property
    def name(self) -> str:
        return "cohere"

    @property
    def model_name(self) -> str:
        return self._model_name

    def is_configured(self) -> bool:
        api_key = os.getenv("COHERE_API_KEY", "")
        return bool(api_key)

    def _make_request(self, url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
        """Make HTTP request using urllib."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def analyze_transcript(self, transcript: List[Dict[str, str]], language: str) -> ProviderResult:
        start_time = time.perf_counter()

        if language not in SUPPORTED_LANGUAGES:
            return ProviderResult(
                success=False,
                error=f"Unsupported language: {language}",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )
        if not transcript or not isinstance(transcript, list):
            return ProviderResult(
                success=False,
                error="Transcript is empty or invalid.",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        effective_prompt = build_effective_prompt(language)

        api_key = os.getenv("COHERE_API_KEY", "")
        if not api_key:
            return ProviderResult(
                success=False,
                error="COHERE_API_KEY not configured",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        # Cohere API v1 chat endpoint format:
        # - message: current user message (required)
        # - chat_history: previous messages (role: USER/CHATBOT, message: text)
        # - preamble: system prompt
        # - model: model name
        chat_history = []
        last_user_message = None

        for entry in transcript:
            if entry["speaker"] == "Patient":
                role = "USER"
            else:
                role = "CHATBOT"

            if last_user_message is None:
                last_user_message = entry["text"]
            else:
                chat_history.append({"role": role, "message": entry["text"]})

        if last_user_message is None:
            last_user_message = "Analyze this conversation."

        url = "https://api.cohere.ai/v1/chat"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model_name,
            "message": last_user_message,
            "chat_history": chat_history,
            "preamble": effective_prompt,
            "temperature": EVALUATION_TEMPERATURE,
            "response_format": {"type": "json_object"},
        }

        try:
            response = self._make_request(url, headers, payload)
            text = response.get("text", "")
            if not text:
                text = response.get("message", {}).get("content", [{}])[0].get("text", "")
            data = json.loads(text)

        except json.JSONDecodeError:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return ProviderResult(
                success=False,
                error="The AI provider returned invalid output (invalid JSON).",
                latency_ms=latency_ms,
            )
        except urllib.error.HTTPError as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_body = e.read().decode("utf-8", errors="ignore")
            return ProviderResult(
                success=False,
                error=f"HTTP {e.code}: {error_body[:200]}",
                latency_ms=latency_ms,
            )
        except Exception as error:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_message = str(error)
            if api_key and api_key in error_message:
                error_message = error_message.replace(api_key, "[REDACTED]")
            logger.warning(
                "Cohere analysis failed: type=%s, message=%s",
                type(error).__name__,
                error_message,
            )
            return ProviderResult(
                success=False,
                error=error_message,
                latency_ms=latency_ms,
            )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        validated = _validate_full_analysis(data)
        if validated is None:
            return ProviderResult(
                success=False,
                error="The AI provider returned invalid output.",
                latency_ms=latency_ms,
            )

        return ProviderResult(success=True, output=validated, latency_ms=latency_ms)


class GroqProvider(BaseProvider):
    """Groq provider using OpenAI-compatible REST API."""

    def __init__(self):
        self._model_name = "openai/gpt-oss-120b"

    @property
    def name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return self._model_name

    def is_configured(self) -> bool:
        api_key = os.getenv("GROQ_API_KEY", "")
        return bool(api_key)

    def _make_request(self, url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
        """Make HTTP request using urllib."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def analyze_transcript(self, transcript: List[Dict[str, str]], language: str) -> ProviderResult:
        start_time = time.perf_counter()

        if language not in SUPPORTED_LANGUAGES:
            return ProviderResult(
                success=False,
                error=f"Unsupported language: {language}",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )
        if not transcript or not isinstance(transcript, list):
            return ProviderResult(
                success=False,
                error="Transcript is empty or invalid.",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        effective_prompt = build_effective_prompt(language)

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            return ProviderResult(
                success=False,
                error="GROQ_API_KEY not configured",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MindWell-Provider-Test/1.0",
        }
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": effective_prompt},
                {"role": "user", "content": json.dumps(transcript, ensure_ascii=False)},
            ],
            "temperature": EVALUATION_TEMPERATURE,
            "response_format": {"type": "json_object"},
        }

        try:
            response = self._make_request(url, headers, payload)
            content = response["choices"][0]["message"]["content"]
            data = json.loads(content)

        except json.JSONDecodeError:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return ProviderResult(
                success=False,
                error="The AI provider returned invalid output (invalid JSON).",
                latency_ms=latency_ms,
            )
        except urllib.error.HTTPError as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_body = e.read().decode("utf-8", errors="ignore")
            return ProviderResult(
                success=False,
                error=f"HTTP {e.code}: {error_body[:200]}",
                latency_ms=latency_ms,
            )
        except Exception as error:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_message = str(error)
            if api_key and api_key in error_message:
                error_message = error_message.replace(api_key, "[REDACTED]")
            logger.warning(
                "Groq analysis failed: type=%s, message=%s",
                type(error).__name__,
                error_message,
            )
            return ProviderResult(
                success=False,
                error=error_message,
                latency_ms=latency_ms,
            )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        validated = _validate_full_analysis(data)
        if validated is None:
            return ProviderResult(
                success=False,
                error="The AI provider returned invalid output.",
                latency_ms=latency_ms,
            )

        return ProviderResult(success=True, output=validated, latency_ms=latency_ms)


# Provider registry for evaluation script
PROVIDER_REGISTRY = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "cohere": CohereProvider,
    "groq": GroqProvider,
}


def get_provider(provider_name: str) -> BaseProvider:
    """Get provider instance by name."""
    if provider_name not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(PROVIDER_REGISTRY.keys())}")
    return PROVIDER_REGISTRY[provider_name]()


def list_available_providers() -> List[str]:
    """Return list of provider names that are configured and available."""
    available = []
    for name, cls in PROVIDER_REGISTRY.items():
        try:
            provider = cls()
            if provider.is_configured():
                available.append(name)
        except Exception:
            pass
    return available