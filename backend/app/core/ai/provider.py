"""Cloudflare Workers AI text-to-image call (ADR-022). Only the user's typed prompt is sent.

Uses the standard library HTTP client in a worker thread (no new dependency). Tests replace
`generate` with a fake through `app.state.ai_generate`."""

import asyncio
import base64
import json
import re
import urllib.error
import urllib.request

from app.core.config import Settings
from app.core.errors import AppError

MODEL = "@cf/black-forest-labs/flux-1-schnell"
STEPS = 4  # the cheapest setting that still gives a usable photo
TIMEOUT_SECONDS = 60


class AiProviderError(AppError):
    status_code, code = 502, "ai_provider_error"


def _call(settings: Settings, prompt: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{32}", settings.ai_cf_account_id):
        raise AiProviderError("bad_account_id")  # never build a URL from unexpected text
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{settings.ai_cf_account_id}/ai/run/{MODEL}"
    )
    body = json.dumps({"prompt": prompt, "steps": STEPS}).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.ai_cf_api_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.loads(response.read(16 * 1024 * 1024))
        return base64.b64decode(payload["result"]["image"], validate=True)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, TypeError):
        # Never echo the provider's response: it could contain account details.
        raise AiProviderError() from None


async def generate(settings: Settings, prompt: str) -> bytes:
    return await asyncio.to_thread(_call, settings, prompt)
