"""Speech-to-text, for the self-assembled route.

This file exists because this example runs the conversation itself. A Voho
voice agent already does the listening — it hears the caller in Saudi Arabic,
decides what to do and speaks back, and none of this file is involved. Reach
for it when you are driving the conversation from your own code and only using
Voho for the voice.

Whatever you use has to be good at Saudi Arabic specifically. A model that
scores well on Modern Standard can still mishear Najdi, and on a live call a
misheard detail is a wasted booking.
"""

from __future__ import annotations

import os

import requests

PROVIDER = os.getenv("STT_PROVIDER", "twilio")
LANGUAGE = os.getenv("STT_LANGUAGE", "ar-SA")


class STTError(RuntimeError):
    pass


def transcribe(audio: bytes, *, content_type: str = "audio/wav") -> str:
    """Turn caller audio into text."""
    if PROVIDER == "openai":
        return _openai_whisper(audio, content_type)
    if PROVIDER == "custom":
        return _custom_endpoint(audio, content_type)
    raise STTError(
        f"STT_PROVIDER={PROVIDER!r} does not transcribe audio directly. "
        "With Twilio, the transcript arrives in the webhook as SpeechResult — "
        "see app.py."
    )


def _openai_whisper(audio: bytes, content_type: str) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise STTError("OPENAI_API_KEY is not set")
    r = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("turn.wav", audio, content_type)},
        data={"model": os.getenv("OPENAI_STT_MODEL", "whisper-1"), "language": "ar"},
        timeout=60,
    )
    if r.status_code != 200:
        raise STTError(f"{r.status_code} from Whisper: {r.text[:300]}")
    return r.json()["text"]


def _custom_endpoint(audio: bytes, content_type: str) -> str:
    """Anything that accepts audio and returns {"text": "..."}.

    This is the hook for an on-premise model. Saudi enterprises frequently
    require that call audio never leaves the building, and a self-hosted
    recogniser behind STT_URL is how that requirement is met.
    """
    url = os.getenv("STT_URL")
    if not url:
        raise STTError("STT_URL is not set")
    r = requests.post(
        url,
        headers={"Content-Type": content_type, "X-Language": LANGUAGE},
        data=audio,
        timeout=60,
    )
    if r.status_code != 200:
        raise STTError(f"{r.status_code} from {url}: {r.text[:300]}")
    return r.json()["text"]
