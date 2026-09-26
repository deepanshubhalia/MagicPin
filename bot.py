"""
magicpin AI Challenge — Vera Message Engine (bot.py)
Official Entry Point and Web Server.

Exposes required public endpoints:
GET  /healthz & GET  /v1/healthz
GET  /metadata & GET /v1/metadata
POST /context & POST /v1/context
POST /tick & POST    /v1/tick
POST /reply & POST   /v1/reply

Exported public function:
compose(category, merchant, trigger, customer=None) -> dict
"""

from __future__ import annotations
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from engine.composer import compose as engine_compose
from engine.reply import ReplyHandler
from engine.store import ContextStore, ConversationStore, SuppressionStore

START_TIME = time.time()

# In-memory stores
context_store = ContextStore()
suppression_store = SuppressionStore()
conversation_store = ConversationStore()
reply_handler = ReplyHandler(conversation_store, suppression_store)

app = FastAPI(title="Vera Message Engine", version="1.0.0")


# -----------------------------------------------------------------------------
# PUBLIC API COMPOSITION FUNCTION (REQUIRED BY CHALLENGE BRIEF §7.1)
# -----------------------------------------------------------------------------

def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    """
    Inputs are the dicts loaded from dataset JSON.
    Returns dict with keys: body, cta, send_as, suppression_key, rationale.
    Deterministic, grounded in context, completes in < 30ms.
    """
    return engine_compose(category, merchant, trigger, customer)


# -----------------------------------------------------------------------------
# PYDANTIC MODELS FOR HTTP ENDPOINTS
# -----------------------------------------------------------------------------

class ContextPushBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


class TickBody(BaseModel):
    now: Optional[str] = None
    available_triggers: List[str] = []


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


# -----------------------------------------------------------------------------
# ENDPOINT IMPLEMENTATIONS (SUPPORTING BOTH /v1/* AND ROOT PATHS)
# -----------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "service": "Vera Message Engine",
        "status": "ok",
        "endpoints": {
            "healthz": "/v1/healthz",
            "metadata": "/v1/metadata",
            "context": "/v1/context",
            "tick": "/v1/tick",
            "reply": "/v1/reply",
            "docs": "/docs"
        }
    }


@app.get("/healthz")
@app.get("/v1/healthz")

async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": context_store.counts(),
    }


@app.get("/metadata")
@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Vera Engine",
        "team_members": ["magicpin AI Team"],
        "model": "context-grounded-deterministic-engine",
        "approach": "signal extraction with category-voice and merchant-fit composition",
        "contact_email": "vera@magicpin.in",
        "version": "1.0.0",
        "submitted_at": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/context")
@app.post("/v1/context")
async def push_context(body: ContextPushBody):
    accepted, ack_id_or_reason, current_v = context_store.push(
        scope=body.scope,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
        delivered_at=body.delivered_at,
    )
    if not accepted:
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": ack_id_or_reason,
                "current_version": current_v,
            },
        )
    return {
        "accepted": True,
        "ack_id": ack_id_or_reason,
        "stored_at": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/tick")
@app.post("/v1/tick")
async def tick(body: TickBody):
    actions = []
    triggers_to_process = body.available_triggers

    # If no triggers specified in tick, check all stored triggers
    if not triggers_to_process:
        triggers_to_process = [
            cid for (scope, cid) in context_store.counts().keys() if scope == "trigger"
        ] if hasattr(context_store, "keys") else []

    for trg_id in triggers_to_process:
        trg = context_store.get("trigger", trg_id)
        if not trg:
            continue

        supp_key = trg.get("suppression_key", "")
        if supp_key and suppression_store.is_suppressed(supp_key):
            continue

        merchant_id = trg.get("merchant_id")
        merchant = context_store.get("merchant", merchant_id) if merchant_id else None
        if not merchant:
            continue

        category_slug = merchant.get("category_slug", "dentists")
        category = context_store.get("category", category_slug)

        customer_id = trg.get("customer_id")
        customer = context_store.get("customer", customer_id) if customer_id else None

        # Compose message
        composed = compose(category, merchant, trg, customer)

        # Record suppression
        if composed.get("suppression_key"):
            suppression_store.suppress(composed["suppression_key"])

        actions.append({
            "conversation_id": f"conv_{merchant_id}_{trg_id}",
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": f"vera_{trg.get('kind', 'generic')}_v1",
            "template_params": [merchant.get("identity", {}).get("name", ""), composed["body"][:40]],
            "body": composed["body"],
            "cta": composed.get("cta", "open_ended"),
            "suppression_key": composed.get("suppression_key", ""),
            "rationale": composed.get("rationale", ""),
        })

    return {"actions": actions}


@app.post("/reply")
@app.post("/v1/reply")
async def reply(body: ReplyBody):
    resp = reply_handler.handle_reply(
        conversation_id=body.conversation_id,
        message=body.message,
        turn_number=body.turn_number,
        merchant_id=body.merchant_id,
        customer_id=body.customer_id,
        from_role=body.from_role,
    )
    return resp
