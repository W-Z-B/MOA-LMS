"""Where the model runs (decision D5): one interface, and one implementation for a model GSA hosts.

The LMS calls a URL GSA configures (AI_OLLAMA_URL), speaking Ollama's HTTP API (Ollama is MIT licensed and
runs open models on GSA's own server). No outside AI service is implemented: using one would send data out
of Guyana and needs a new decision with its own impact assessment (ADR 0007). Another provider would be a
new class with the same generate() method, added by a reviewed change.
"""

import base64
import json
import urllib.error
import urllib.request
from typing import Protocol
from urllib.parse import urlparse

from django.conf import settings

from core import outbound


class ProviderError(Exception):
    """The model could not be reached, or did not answer."""


class Provider(Protocol):
    name: str

    def generate(
        self, prompt: str, *, system: str = "", images: list[bytes] | None = None, json_output: bool = False
    ) -> str: ...


class OllamaProvider:
    """A model served by Ollama on GSA's own server: POST {url}/api/generate, without streaming."""

    def __init__(self, url: str, model: str, timeout: int):
        if urlparse(url).scheme not in ("http", "https"):
            raise ProviderError("AI_OLLAMA_URL must be an http or https address.")
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
        self.name = f"ollama:{model}"

    def generate(
        self, prompt: str, *, system: str = "", images: list[bytes] | None = None, json_output: bool = False
    ) -> str:
        body = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if images:
            body["images"] = [base64.b64encode(image).decode() for image in images]
        if json_output:
            body["format"] = "json"
        request = urllib.request.Request(  # noqa: S310 - the scheme is checked in __init__
            f"{self.url}/api/generate",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            # GSA's own server, at the address set in the environment (core.outbound: no redirects).
            with outbound.urlopen(
                request, timeout=self.timeout, configured=True, schemes=("http", "https")
            ) as response:
                answer = json.loads(response.read(2_000_000).decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise ProviderError("The AI model could not be reached.") from error
        text = answer.get("response") if isinstance(answer, dict) else None
        if not isinstance(text, str):
            raise ProviderError("The AI model did not answer.")
        return text.strip()


def enabled() -> bool:
    """Whether GSA has switched AI on and said where its model is."""
    return bool(settings.AI_ENABLED and settings.AI_OLLAMA_URL and settings.AI_MODEL)


def provider(*, vision: bool = False) -> Provider | None:
    """The configured provider, or None while AI is off. Pictures need a model that reads them."""
    if not enabled():
        return None
    model = settings.AI_VISION_MODEL if vision else settings.AI_MODEL
    if not model:
        return None
    return OllamaProvider(settings.AI_OLLAMA_URL, model, settings.AI_TIMEOUT_SECONDS)
