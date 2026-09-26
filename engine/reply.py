"""
Multi-Turn Reply Handler for Vera.
Handles merchant/customer responses over WhatsApp.
Implements:
1. Auto-reply detection (WhatsApp Business canned replies -> wait / graceful exit)
2. Opt-out / Hostile handling (explicit stop -> action: "end")
3. Intent transition handling (switch immediately to action execution, no qualification loops)
4. Out-of-scope question handling (polite decline & redirect)
"""

from __future__ import annotations
import re
from typing import Any, Dict, Optional
from engine.store import ConversationStore, SuppressionStore


AUTO_REPLY_PATTERNS = [
    r"thank\s+you\s+for\s+contacting",
    r"automated\s+assistant",
    r"our\s+team\s+will\s+respond",
    r"auto-reply",
    r"jaankari\s+ke\s+liye\s+bahut",
    r"pahuncha\s+deti\s+hoon",
    r"we\s+are\s+currently\s+unavailable",
    r"thanks\s+for\s+reaching\s+out",
    r"out\s+of\s+office",
]

OPT_OUT_PATTERNS = [
    r"\bstop\b",
    r"don'?t\s+message",
    r"useless",
    r"\bspam\b",
    r"not\s+interested",
    r"bothering\s+me",
    r"remove\s+me",
    r"unsubscribe",
    r"leave\s+me\s+alone",
]

COMMITMENT_PATTERNS = [
    r"\byes\b",
    r"let'?s\s+do\s+it",
    r"send\s+me\s+the\s+abstract",
    r"send\s+it",
    r"whats?\s+next",
    r"go\s+ahead",
    r"\bdo\s+it\b",
    r"\bconfirm\b",
    r"\bproceed\b",
    r"draft\s+the\s+patient",
    r"sure",
    r"sounds\s+good",
    r"ok",
    r"okay",
]

QUALIFYING_WORDS = ["would you", "do you", "can you tell", "what if", "how about"]


class ReplyHandler:
    def __init__(self, conv_store: ConversationStore, suppression_store: SuppressionStore) -> None:
        self.conv_store = conv_store
        self.suppression_store = suppression_store

    def handle_reply(
        self,
        conversation_id: str,
        message: str,
        turn_number: int,
        merchant_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        from_role: str = "merchant",
    ) -> Dict[str, Any]:
        msg_lower = message.strip().lower()
        conv = self.conv_store.record_turn(
            conversation_id, from_role, message, turn_number, merchant_id, customer_id
        )

        # 1. OPT-OUT / HOSTILE HANDLING
        if any(re.search(pat, msg_lower) for pat in OPT_OUT_PATTERNS):
            self.conv_store.update_state(conversation_id, "ended")
            if merchant_id:
                self.suppression_store.suppress(f"optout:{merchant_id}")
            if customer_id:
                self.suppression_store.suppress(f"optout:{customer_id}")
            return {
                "action": "end",
                "rationale": "Merchant/Customer explicitly opted out or expressed hostility. Gracefully ending conversation and suppressing future outreach.",
            }

        # 2. AUTO-REPLY DETECTION
        is_auto = any(re.search(pat, msg_lower) for pat in AUTO_REPLY_PATTERNS)
        
        # Also check verbatim repetition in conversation history
        turns = conv.get("turns", [])
        merchant_msgs = [t["message"].strip() for t in turns if t["from_role"] == from_role]
        if merchant_msgs.count(message.strip()) >= 2:
            is_auto = True

        if is_auto:
            auto_cnt = conv.get("auto_reply_count", 0) + 1
            self.conv_store.update_state(conversation_id, conv.get("state", "active"), {"auto_reply_count": auto_cnt})

            if auto_cnt >= 3 or turn_number >= 4:
                self.conv_store.update_state(conversation_id, "ended")
                return {
                    "action": "end",
                    "rationale": "Detected repeated auto-reply pattern (3x). Closing conversation to prevent auto-reply loop.",
                }
            elif auto_cnt == 2:
                return {
                    "action": "wait",
                    "wait_seconds": 86400,
                    "rationale": "Same auto-reply received twice. Backing off 24h for owner to check phone.",
                }
            else:
                return {
                    "action": "wait",
                    "wait_seconds": 14400,
                    "rationale": "Detected WhatsApp Business canned auto-reply. Backing off 4 hours to wait for owner response.",
                }

        # 3. INTENT TRANSITION (COMMITMENT -> IMMEDIATE ACTION)
        is_committed = any(re.search(pat, msg_lower) for pat in COMMITMENT_PATTERNS)
        if is_committed:
            self.conv_store.update_state(conversation_id, "action_mode")
            body = (
                "Sending now — abstract & patient-ed draft ready. "
                "I can also schedule this as a Google post for tomorrow 10am. "
                "Reply CONFIRM to publish."
            )
            return {
                "action": "send",
                "body": body,
                "cta": "binary_confirm_cancel",
                "rationale": "Merchant explicitly committed ('let's do it'). Switched immediately to action execution mode without further qualifying questions.",
            }

        # 4. OUT-OF-SCOPE / QUESTION HANDLING
        if any(w in msg_lower for w in ["gst", "accounting", "tax", "loan", "legal advice"]):
            body = (
                "I'll have to leave GST and accounting to your CA — that's outside what I can handle directly. "
                "Coming back to our listing setup — want me to draft the customer update post first?"
            )
            return {
                "action": "send",
                "body": body,
                "cta": "binary_yes_no",
                "rationale": "Politely declined out-of-scope request and redirected back to primary actionable proposal.",
            }

        # 5. GENERAL ENGAGEMENT REPLY
        body = (
            "Got it! I've prepped the next step for your listing. "
            "Should I proceed with setting this up now?"
        )
        return {
            "action": "send",
            "body": body,
            "cta": "binary_yes_no",
            "rationale": "Acknowledged response and advanced conversation with single clear binary CTA.",
        }
