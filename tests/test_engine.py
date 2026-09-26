"""
Unit tests for Vera Message Engine.
Run with: ./venv/bin/pytest tests/test_engine.py
"""

import json
from pathlib import Path
import pytest
from bot import compose
from engine.store import ContextStore, ConversationStore, SuppressionStore
from engine.reply import ReplyHandler


DATASET_DIR = Path("./dataset/expanded")


@pytest.fixture
def dataset():
    categories = {}
    for f in (DATASET_DIR / "categories").glob("*.json"):
        d = json.load(open(f))
        categories[d["slug"]] = d

    merchants = {}
    for f in (DATASET_DIR / "merchants").glob("*.json"):
        d = json.load(open(f))
        merchants[d["merchant_id"]] = d

    customers = {}
    for f in (DATASET_DIR / "customers").glob("*.json"):
        d = json.load(open(f))
        customers[d["customer_id"]] = d

    triggers = {}
    for f in (DATASET_DIR / "triggers").glob("*.json"):
        d = json.load(open(f))
        triggers[d["id"]] = d

    return {
        "categories": categories,
        "merchants": merchants,
        "customers": customers,
        "triggers": triggers,
    }


def test_compose_dentist_research_digest(dataset):
    cat = dataset["categories"]["dentists"]
    # Pick a dentist merchant
    m = next(m for m in dataset["merchants"].values() if m["category_slug"] == "dentists")
    trg = {
        "id": "trg_test_01",
        "scope": "merchant",
        "kind": "research_digest",
        "merchant_id": m["merchant_id"],
        "payload": {"category": "dentists", "top_item_id": cat["digest"][0]["id"]},
        "urgency": 2,
        "suppression_key": "research:dentists:2026-W17",
    }

    res = compose(cat, m, trg)
    assert "body" in res
    assert "cta" in res
    assert res["send_as"] == "vera"
    assert "JIDA" in res["body"] or "Journal" in res["body"]
    assert len(res["body"]) > 20
    assert "guaranteed" not in res["body"].lower()


def test_compose_customer_facing_recall(dataset):
    cat = dataset["categories"]["dentists"]
    m = next(m for m in dataset["merchants"].values() if m["category_slug"] == "dentists")
    c = next(c for c in dataset["customers"].values() if c["merchant_id"] == m["merchant_id"])
    trg = {
        "id": "trg_test_02",
        "scope": "customer",
        "kind": "recall_due",
        "merchant_id": m["merchant_id"],
        "customer_id": c["customer_id"],
        "urgency": 3,
        "suppression_key": f"recall:{c['customer_id']}",
    }

    res = compose(cat, m, trg, c)
    assert res["send_as"] == "merchant_on_behalf"
    assert c["identity"]["name"] in res["body"]
    assert "recall" in res["body"].lower() or "visit" in res["body"].lower()


def test_context_store_idempotency():
    store = ContextStore()
    payload = {"slug": "dentists", "title": "Dentists"}

    # Push v1 -> Accepted
    acc, ack, _ = store.push("category", "dentists", 1, payload)
    assert acc is True
    assert ack == "ack_dentists_v1"

    # Push v1 again -> Accepted (idempotent no-op)
    acc, ack, _ = store.push("category", "dentists", 1, payload)
    assert acc is True
    assert ack == "ack_dentists_v1"

    # Push v2 -> Accepted (atomically replace)
    payload_v2 = {"slug": "dentists", "title": "Dentists Updated"}
    acc, ack, _ = store.push("category", "dentists", 2, payload_v2)
    assert acc is True
    assert ack == "ack_dentists_v2"
    assert store.get("category", "dentists")["title"] == "Dentists Updated"

    # Push v1 (stale version) -> Rejected (stale_version)
    acc, reason, cur_v = store.push("category", "dentists", 1, payload)
    assert acc is False
    assert reason == "stale_version"
    assert cur_v == 2


def test_reply_auto_reply_detection():
    c_store = ConversationStore()
    s_store = SuppressionStore()
    handler = ReplyHandler(c_store, s_store)

    auto_msg = "Thank you for contacting us! Our team will respond shortly."

    # Turn 1
    res1 = handler.handle_reply("conv_auto_1", auto_msg, 2, "m_001")
    assert res1["action"] == "wait"
    assert res1["wait_seconds"] == 14400

    # Turn 2 (same auto-reply)
    res2 = handler.handle_reply("conv_auto_1", auto_msg, 3, "m_001")
    assert res2["action"] == "wait"
    assert res2["wait_seconds"] == 86400

    # Turn 3 (same auto-reply -> end)
    res3 = handler.handle_reply("conv_auto_1", auto_msg, 4, "m_001")
    assert res3["action"] == "end"


def test_reply_intent_transition():
    c_store = ConversationStore()
    s_store = SuppressionStore()
    handler = ReplyHandler(c_store, s_store)

    res = handler.handle_reply("conv_intent_1", "Ok let's do it. What's next?", 2, "m_001")
    assert res["action"] == "send"
    assert "Sending" in res["body"] or "ready" in res["body"]
    assert not any(w in res["body"].lower() for w in ["would you like to know", "can you tell me"])


def test_reply_opt_out_hostile():
    c_store = ConversationStore()
    s_store = SuppressionStore()
    handler = ReplyHandler(c_store, s_store)

    res = handler.handle_reply("conv_optout_1", "Stop messaging me. This is useless spam.", 2, "m_001")
    assert res["action"] == "end"
    assert s_store.is_suppressed("optout:m_001")


def test_determinism(dataset):
    cat = dataset["categories"]["dentists"]
    m = next(m for m in dataset["merchants"].values() if m["category_slug"] == "dentists")
    trg = {
        "id": "trg_det_01",
        "scope": "merchant",
        "kind": "research_digest",
        "merchant_id": m["merchant_id"],
        "payload": {"category": "dentists", "top_item_id": cat["digest"][0]["id"]},
        "urgency": 2,
        "suppression_key": "research:dentists:2026-W17",
    }

    first_run = compose(cat, m, trg)
    for _ in range(50):
        run = compose(cat, m, trg)
        assert run == first_run, "Non-deterministic output detected!"

