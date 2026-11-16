"""Focused unit tests for OpenAI/Groq response hardening (finding F1).

All provider responses are mocked; no real API calls are made.
Covers _ask_openai, _ask_groq, and the OpenAI/Groq branch of _ask_json_content.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from ai_service.services import (
    AIServiceConfigurationError,
    _ask_groq,
    _ask_json_content,
    _ask_openai,
)


def _client_returning(response):
    """Patch the right client factory to return ``response`` from create()."""
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _valid_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class _BaseProviderResponseTests:
    provider = None  # "openai" | "groq"
    ask = None  # function under test

    def _client_patch(self):
        if self.provider == "groq":
            return patch("ai_service.services.get_groq_client")
        return patch("ai_service.services.get_openai_client")

    def _call(self, response):
        with self._client_patch() as get_client:
            get_client.return_value = _client_returning(response)
            return self.ask("system", "text")

    def test_empty_choices_raises_configuration_error(self):
        with self.assertRaises(AIServiceConfigurationError) as ctx:
            self._call(SimpleNamespace(choices=[]))
        self.assertIn(self.provider, str(ctx.exception))
        self.assertIn("no choices", str(ctx.exception))

    def test_missing_choices_raises_configuration_error(self):
        with self.assertRaises(AIServiceConfigurationError) as ctx:
            self._call(SimpleNamespace())
        self.assertIn("no choices", str(ctx.exception))

    def test_none_message_raises_configuration_error(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=None)])
        with self.assertRaises(AIServiceConfigurationError) as ctx:
            self._call(response)
        self.assertIn("no message", str(ctx.exception))

    def test_none_content_raises_configuration_error(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        )
        with self.assertRaises(AIServiceConfigurationError) as ctx:
            self._call(response)
        self.assertIn("empty content", str(ctx.exception))

    def test_empty_content_raises_configuration_error(self):
        with self.assertRaises(AIServiceConfigurationError) as ctx:
            self._call(_valid_response(""))
        self.assertIn("empty content", str(ctx.exception))

    def test_whitespace_only_content_raises_configuration_error(self):
        with self.assertRaises(AIServiceConfigurationError) as ctx:
            self._call(_valid_response("   \n\t  "))
        self.assertIn("empty content", str(ctx.exception))

    def test_valid_json_content_parses(self):
        result = self._call(_valid_response('{"summary": "ok", "risk_level": "low"}'))
        self.assertEqual(result, {"summary": "ok", "risk_level": "low"})

    def test_invalid_json_raises_configuration_error(self):
        with self.assertRaises(AIServiceConfigurationError) as ctx:
            self._call(_valid_response("not json"))
        self.assertIn("invalid JSON", str(ctx.exception))


class AskOpenAITests(_BaseProviderResponseTests, TestCase):
    provider = "openai"
    ask = staticmethod(_ask_openai)


class AskGroqTests(_BaseProviderResponseTests, TestCase):
    provider = "groq"
    ask = staticmethod(_ask_groq)


class _BaseJsonContentTests(_BaseProviderResponseTests):
    def _call(self, response):
        with self._client_patch() as get_client:
            get_client.return_value = _client_returning(response)
            return _ask_json_content("system", "text", provider=self.provider)


class AskJsonContentOpenAITests(_BaseJsonContentTests, TestCase):
    provider = "openai"
    ask = staticmethod(_ask_json_content)


class AskJsonContentGroqTests(_BaseJsonContentTests, TestCase):
    provider = "groq"
    ask = staticmethod(_ask_json_content)