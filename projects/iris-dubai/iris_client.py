"""
iris_client.py
================
Minimal HTTP client for exercising IRIS Dubai's real, unmodified API —
login, create a conversation, send a message, read the streamed result.
No IRIS backend code is touched; this only calls endpoints that already
exist (see the README for exactly which ones).

Each golden query gets its OWN fresh conversation/thread — deliberately,
so unrelated golden queries never share STM/chat history with each other.
"""
import json
import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


def login(base_url: str, email: str, password: str) -> str:
    resp = requests.post(f"{base_url}/auth/login", json={"email": email, "password": password}, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_conversation(base_url: str, token: str) -> str:
    resp = requests.post(
        f"{base_url}/chat/conversation",
        headers={"Authorization": f"Bearer {token}"},
        json={},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def send_message(base_url: str, token: str, chat_session_id: str, message: str, timeout: int = 120) -> Dict[str, Any]:
    """POSTs to the SSE /chat/send endpoint and returns the final event's
    payload — {"thread_id": ..., "response": ..., "message_id": ...} at
    minimum. `thread_id` is used to look the trace back up in Langfuse."""
    resp = requests.post(
        f"{base_url}/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": message, "chat_session_id": chat_session_id, "deep_thinking": False},
        stream=True,
        timeout=timeout,
    )
    resp.raise_for_status()

    final_payload = None
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        event = json.loads(line[len("data: "):])
        if event.get("type") == "final":
            final_payload = event
        elif event.get("type") == "error":
            raise RuntimeError(f"IRIS returned an error event: {event.get('content')}")

    if final_payload is None:
        raise RuntimeError("Stream ended without a 'final' event")
    return final_payload
