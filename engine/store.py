"""
Context and State Management Store for Vera Message Engine.
Thread-safe in-memory storage supporting:
- Idempotent version replacement per (scope, context_id)
- Suppression state management
- Conversation history tracking
"""

from __future__ import annotations
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class ContextStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Storage key: (scope, context_id) -> {"version": int, "payload": dict, "delivered_at": str}
        self._contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def push(
        self, scope: str, context_id: str, version: int, payload: Dict[str, Any], delivered_at: Optional[str] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Push context with version check.
        Returns (accepted, reason_or_ack, current_version_if_rejected).
        """
        with self._lock:
            key = (scope, context_id)
            existing = self._contexts.get(key)
            if existing is not None and existing["version"] > version:
                return False, "stale_version", existing["version"]
            
            self._contexts[key] = {
                "version": version,
                "payload": payload,
                "delivered_at": delivered_at or datetime.utcnow().isoformat() + "Z",
                "stored_at": datetime.utcnow().isoformat() + "Z",
            }
            ack_id = f"ack_{context_id}_v{version}"
            return True, ack_id, None

    def get(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._contexts.get((scope, context_id))
            return data["payload"] if data else None

    def get_by_merchant_id(self, merchant_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._contexts.get(("merchant", merchant_id))
            return data["payload"] if data else None

    def get_category_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._contexts.get(("category", slug))
            return data["payload"] if data else None

    def counts(self) -> Dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for (scope, _), _ in self._contexts.items():
                if scope in counts:
                    counts[scope] += 1
        return counts

    def clear(self) -> None:
        with self._lock:
            self._contexts.clear()


class SuppressionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suppressed_keys: Dict[str, str] = {}  # key -> suppressed_at timestamp

    def is_suppressed(self, key: str) -> bool:
        if not key:
            return False
        with self._lock:
            return key in self._suppressed_keys

    def suppress(self, key: str) -> None:
        if not key:
            return
        with self._lock:
            self._suppressed_keys[key] = datetime.utcnow().isoformat() + "Z"

    def clear(self) -> None:
        with self._lock:
            self._suppressed_keys.clear()


class ConversationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # conv_id -> dict of metadata and turns
        self._conversations: Dict[str, Dict[str, Any]] = {}

    def record_turn(
        self,
        conversation_id: str,
        from_role: str,
        message: str,
        turn_number: int,
        merchant_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if conversation_id not in self._conversations:
                self._conversations[conversation_id] = {
                    "conversation_id": conversation_id,
                    "merchant_id": merchant_id,
                    "customer_id": customer_id,
                    "state": "active",  # active, waiting, ended
                    "auto_reply_count": 0,
                    "turns": [],
                    "last_bot_action": None,
                    "last_trigger_id": None,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                }
            
            conv = self._conversations[conversation_id]
            if merchant_id:
                conv["merchant_id"] = merchant_id
            if customer_id:
                conv["customer_id"] = customer_id
            
            turn_data = {
                "from_role": from_role,
                "message": message,
                "turn_number": turn_number,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            if meta:
                turn_data.update(meta)
            conv["turns"].append(turn_data)
            return conv

    def update_state(self, conversation_id: str, state: str, meta: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            if conversation_id in self._conversations:
                conv = self._conversations[conversation_id]
                conv["state"] = state
                if meta:
                    conv.update(meta)

    def get(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._conversations.get(conversation_id)

    def clear(self) -> None:
        with self._lock:
            self._conversations.clear()
