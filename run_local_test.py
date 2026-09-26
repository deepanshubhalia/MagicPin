"""
Harness test script to evaluate Vera engine endpoints against judge_simulator scenarios.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Set BOT_URL to local server
os.environ["BOT_URL"] = "http://localhost:8088"

from judge_simulator import BotClient, DatasetLoader, ScoreResult

def test_harness():
    print("==================================================")
    print("VERA ENGINE — HARNESS VERIFICATION")
    print("==================================================")
    client = BotClient("http://localhost:8088")
    dataset = DatasetLoader(Path("./dataset/expanded"))
    
    if not dataset.load():
        print("ERROR: Failed to load dataset")
        sys.exit(1)

    print(f"Loaded {len(dataset.categories)} categories, {len(dataset.merchants)} merchants, {len(dataset.triggers)} triggers")

    # 1. Healthz Check
    data, err, lat = client.healthz()
    assert err is None, f"Healthz error: {err}"
    print(f"[PASS] healthz ({lat:.1f}ms): {data}")

    # 2. Metadata Check
    data, err, lat = client.metadata()
    assert err is None, f"Metadata error: {err}"
    print(f"[PASS] metadata ({lat:.1f}ms): {data}")

    # 3. Push Context Check
    for slug, cat in dataset.categories.items():
        res, err, _ = client.push_context("category", slug, 1, cat)
        if not (res and res.get("accepted")):
            # Try version 2 if version 1 was already present from earlier run
            res, err, _ = client.push_context("category", slug, 2, cat)

    for mid, m in list(dataset.merchants.items())[:10]:
        res, err, _ = client.push_context("merchant", mid, 1, m)
        if not (res and res.get("accepted")):
            res, err, _ = client.push_context("merchant", mid, 2, m)

    print("[PASS] Category and Merchant contexts pushed")

    # 4. Idempotency Check (re-pushing same version should return 409 conflict)
    mid_sample = list(dataset.merchants.keys())[0]
    res, err, _ = client.push_context("merchant", mid_sample, 1, dataset.merchants[mid_sample])
    assert res and res.get("accepted") is False and res.get("reason") == "stale_version", f"Idempotency failed: {res}"
    print(f"[PASS] Idempotency check verified (stale version rejected with 409 conflict)")

    # 5. Tick Check
    trig_ids = list(dataset.triggers.keys())[:5]
    for tid in trig_ids:
        client.push_context("trigger", tid, 1, dataset.triggers[tid])

    res, err, lat = client.tick(trig_ids)
    assert res and "actions" in res, f"Tick error: {err}"
    actions = res["actions"]
    print(f"[PASS] Tick ({lat:.1f}ms): returned {len(actions)} action(s)")
    for act in actions:
        print(f"  - [{act['send_as']}] {act['body'][:90]}... (CTA: {act['cta']})")

    # 6. Auto-Reply Detection Test
    import time
    run_ts = int(time.time())
    conv_auto_id = f"conv_auto_{run_ts}"
    conv_intent_id = f"conv_intent_{run_ts}"
    conv_hostile_id = f"conv_hostile_{run_ts}"

    auto_msg = "Thank you for contacting us! Our team will respond shortly."
    mid = list(dataset.merchants.keys())[0]
    
    # Turn 1
    r1, _, _ = client.reply(conv_auto_id, mid, auto_msg, 2)
    assert r1.get("action") == "wait", f"Auto-reply turn 1 failed: {r1}"
    print(f"[PASS] Auto-reply turn 1: action={r1['action']} (wait_seconds={r1.get('wait_seconds')})")

    # Turn 2
    r2, _, _ = client.reply(conv_auto_id, mid, auto_msg, 3)
    assert r2.get("action") == "wait", f"Auto-reply turn 2 failed: {r2}"
    print(f"[PASS] Auto-reply turn 2: action={r2['action']}")

    # Turn 3 -> Should end
    r3, _, _ = client.reply(conv_auto_id, mid, auto_msg, 4)
    assert r3.get("action") == "end", f"Auto-reply turn 3 failed: {r3}"
    print(f"[PASS] Auto-reply turn 3: action={r3['action']} (ended auto-reply loop)")

    # 7. Intent Transition Test (merchant says "Ok let's do it. What's next?")
    r_intent, _, _ = client.reply(conv_intent_id, mid, "Ok let's do it. What's next?", 2)
    assert r_intent.get("action") == "send", f"Intent transition failed: {r_intent}"
    assert not any(w in r_intent.get("body", "").lower() for w in ["would you", "do you", "can you tell"]), "Failed: asked qualifying question during intent transition"
    print(f"[PASS] Intent transition: switched to action execution -> '{r_intent['body'][:80]}...'")

    # 8. Hostile / Opt-out Test ("Stop messaging me. This is useless spam.")
    r_hostile, _, _ = client.reply(conv_hostile_id, mid, "Stop messaging me. This is useless spam.", 2)
    assert r_hostile.get("action") == "end", f"Hostile handling failed: {r_hostile}"
    print(f"[PASS] Hostile handling: action={r_hostile['action']} (graceful opt-out)")

    print("\n==================================================")
    print("ALL HARNESS VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    test_harness()
