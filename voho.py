"""Voho speech client.

Voho does the speaking. Everything it exposes is here: synthesis, the
streaming variant, the voice catalogue, and the Arabic text normaliser that
decides how a number or a date is read out loud.

Speech-to-text is deliberately not in this file — see `stt.py`.
"""

from __future__ import annotations

import os
from typing import Iterator

import requests

BASE_URL = os.getenv("VOHO_BASE_URL", "https://app.voho.ai").rstrip("/")
API_KEY = os.getenv("VOHO_API_KEY", "")

# Najdi is the dialect spoken in Riyadh and central Saudi Arabia. `layla` is
# the reception voice; see https://docs.voho.ai/voices for the rest.
DEFAULT_VOICE = os.getenv("VOHO_VOICE", "layla")

# sada-1 is the faster model and the right default for a live call. nabra-1
# is more expressive and accepts a pitch adjustment.
DEFAULT_MODEL = os.getenv("VOHO_MODEL", "sada-1")

# Telephony carries 8 kHz mulaw. Asking Voho for it directly means no
# transcoding step between the API and the phone line.
TELEPHONY_FORMAT = "mulaw"


class VohoError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not API_KEY:
        raise VohoError(
            "VOHO_API_KEY is not set. Create a token at https://app.voho.ai "
            "under API Tokens and put it in .env"
        )
    return {"Authorization": f"Bearer {API_KEY}"}


def speak(
    text: str,
    *,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    fmt: str = "mp3",
    speed: float | None = None,
) -> bytes:
    """Synthesise `text` and return the audio bytes.

    `text` is capped at 5,000 characters by the API. A conversational turn is
    nowhere near that, so nothing here splits it — if you are reading out a
    long policy document, chunk it on sentence boundaries first.
    """
    payload: dict[str, object] = {"text": text, "voice": voice, "model": model, "format": fmt}
    if speed is not None:
        payload["speed"] = speed

    r = requests.post(
        f"{BASE_URL}/v1/speech", json=payload, headers=_headers(), timeout=30
    )
    if r.status_code != 200:
        raise VohoError(f"{r.status_code} from /v1/speech: {r.text[:300]}")
    return r.content


def speak_stream(
    text: str,
    *,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    fmt: str = "opus",
) -> Iterator[bytes]:
    """Yield audio while it is still being produced.

    On a live call this is the difference between the caller hearing a reply
    in a few hundred milliseconds and hearing it after the whole sentence has
    been rendered.
    """
    r = requests.post(
        f"{BASE_URL}/v1/speech/stream",
        json={"text": text, "voice": voice, "model": model, "format": fmt},
        headers=_headers(),
        stream=True,
        timeout=60,
    )
    if r.status_code != 200:
        raise VohoError(f"{r.status_code} from /v1/speech/stream: {r.text[:300]}")
    for chunk in r.iter_content(chunk_size=4096):
        if chunk:
            yield chunk


def speak_for_phone(text: str, **kw) -> bytes:
    """Synthesis in the format a SIP trunk already carries."""
    return speak(text, fmt=TELEPHONY_FORMAT, **kw)


def voices(dialect: str | None = None) -> list[dict]:
    """The catalogue. Pass `najdi` to see only the Saudi voices."""
    params = {"dialect": dialect} if dialect else {}
    r = requests.get(
        f"{BASE_URL}/v1/voices", params=params, headers=_headers(), timeout=15
    )
    if r.status_code != 200:
        raise VohoError(f"{r.status_code} from /v1/voices: {r.text[:300]}")
    return r.json().get("voices", r.json())


def normalize(text: str) -> str:
    """Expand numbers, dates and abbreviations the way they are spoken.

    Worth calling before you read back a reference number or a time — "٤:٣٠"
    and "APT-20418" are exactly the places a synthesiser guesses wrong.
    """
    r = requests.post(
        f"{BASE_URL}/v1/text/normalize",
        json={"text": text},
        headers=_headers(),
        timeout=15,
    )
    if r.status_code != 200:
        raise VohoError(f"{r.status_code} from /v1/text/normalize: {r.text[:300]}")
    return r.json().get("text", text)
