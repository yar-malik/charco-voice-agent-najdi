"""Flask: the phone line and the order API.

Twilio calls `/voice` when the phone rings and `/voice/turn` for every turn
after that. When the order is finished it is POSTed to whatever `POS_URL`
points at — your point-of-sale system — and also returned on `/api/orders` so
you can watch tickets arrive while testing.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from typing import Dict, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, url_for

load_dotenv()

import agent as agent_mod  # noqa: E402
import voho  # noqa: E402

app = Flask(__name__)

if not voho.has_key():
    # Fail at boot, not on the first caller.
    raise SystemExit(f"\n{voho.MISSING_KEY}\n")

_calls: Dict[str, agent_mod.Agent] = {}
_clips: Dict[str, Tuple[bytes, str]] = {}
_tickets: list[dict] = []
_lock = threading.Lock()

PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
POS_URL = os.getenv("POS_URL", "")


def _clip(text: str) -> str:
    audio = voho.speak(text, fmt="mp3")
    clip_id = secrets.token_urlsafe(12)
    with _lock:
        _clips[clip_id] = (audio, "audio/mpeg")
    path = url_for("clip", clip_id=clip_id)
    return f"{PUBLIC_URL}{path}" if PUBLIC_URL else path


def _twiml(say_url: str, *, listen: bool) -> Response:
    if listen:
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="ar-SA" speechTimeout="auto" action="/voice/turn" method="POST">
    <Play>{say_url}</Play>
  </Gather>
  <Redirect method="POST">/voice/turn</Redirect>
</Response>"""
    else:
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Play>{say_url}</Play>
  <Hangup/>
</Response>"""
    return Response(body, mimetype="text/xml")


@app.post("/voice")
def voice():
    call_sid = request.form.get("CallSid", secrets.token_urlsafe(8))
    convo = agent_mod.Agent(caller=request.form.get("From", "unknown"))
    with _lock:
        _calls[call_sid] = convo
    return _twiml(_clip(convo.greeting()), listen=True)


@app.post("/voice/turn")
def turn():
    call_sid = request.form.get("CallSid", "")
    said = request.form.get("SpeechResult", "").strip()

    with _lock:
        convo = _calls.get(call_sid)
    if convo is None:
        return _twiml(_clip("معليش، صار عندنا خلل تقني. جرب تتصل مرة ثانية."), listen=False)
    if not said:
        return _twiml(_clip("ما سمعتك زين. تقدر تعيد؟"), listen=True)

    answer = convo.reply(said)

    if convo.ticket:
        _submit(convo.ticket)
        return _twiml(_clip(answer), listen=False)
    return _twiml(_clip(answer), listen=True)


@app.get("/clip/<clip_id>")
def clip(clip_id: str):
    with _lock:
        found = _clips.pop(clip_id, None)  # played once, then gone
    if not found:
        return Response(status=404)
    audio, content_type = found
    return Response(audio, mimetype=content_type)


@app.get("/api/orders")
def orders():
    """Every ticket this process has taken. Handy while testing."""
    with _lock:
        return jsonify(_tickets)


@app.post("/api/orders")
def submit_order():
    """Accept a ticket from the Streamlit tester, or from anything else."""
    ticket = request.get_json(force=True, silent=True) or {}
    if not ticket.get("lines"):
        return jsonify({"error": "no lines"}), 400
    _submit(ticket)
    return jsonify({"ok": True, "ticket": ticket.get("ticket")}), 201


@app.get("/health")
def health():
    return {"ok": True, "voice": voho.DEFAULT_VOICE, "tickets": len(_tickets)}


def _submit(ticket: dict) -> None:
    """Record the ticket, and push it to the point-of-sale system."""
    with _lock:
        _tickets.append(ticket)

    if not POS_URL:
        app.logger.info("POS_URL not set, ticket kept locally:\n%s",
                        json.dumps(ticket, ensure_ascii=False, indent=2))
        return
    try:
        requests.post(POS_URL, json=ticket, timeout=10).raise_for_status()
    except Exception as exc:  # noqa: BLE001 — the caller has already hung up
        app.logger.error("POS submit failed for ticket %s: %s", ticket.get("ticket"), exc)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
