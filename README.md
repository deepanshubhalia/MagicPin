# Vera Message Engine — magicpin AI Challenge Submission

## Overview
Vera Message Engine is a deterministic, context-grounded message composition and conversation engine for magicpin's AI assistant Vera. It evaluates structured inputs across four context layers (Category, Merchant, Trigger, and Customer) to compose high-converting WhatsApp messages and manage multi-turn merchant/customer interactions.

## Architecture and Approach
The system follows a modular 4-layer design:
1. Store Layer (`engine/store.py`): In-memory, thread-safe context store supporting atomic version updates and idempotency (`(scope, context_id, version)`), suppression tracking (`SuppressionStore`), and conversation state tracking (`ConversationStore`).
2. Signal Extraction (`engine/signals.py`): Extracts verifiable facts (metrics, percentages, active offer titles/prices, locality, owner first names, language preferences, research citations, and category taboos) from input JSON structures without inventing data.
3. Message Composition (`engine/composer.py`): Composes messages by mapping extracted signals to category-appropriate voice profiles (clinical/peer for dentists, operator-to-operator for restaurants/gyms, warm for salons/pharmacies). Appends exactly one clear call-to-action (CTA) to every outbound message.
4. Multi-Turn Reply Handler (`engine/reply.py`): Handles WhatsApp replies by detecting canned auto-replies, hostile opt-outs, out-of-scope requests, and intent transitions.

## Decision Logic
The engine ranks triggers and signals using a deterministic priority hierarchy:
1. Safety & Compliance Alerts (urgent product recalls, dose limit revisions)
2. Time-Sensitive Events (IPL match day, upcoming local festivals, weather alerts)
3. Performance Anomalies (7-day view or call drops and spikes)
4. Research Digests (category research items with source citations)
5. Customer Winback & Recalls (6-month cleaning recall, chronic refill due)
6. Active Planning & Recurring Nudges (weekly curious asks, dormancy alerts, competitor listings)

## Deterministic Behavior
- Zero randomness: Temperature is effectively 0 across signal extraction and composition.
- Zero hallucination: All numbers, prices, dates, sources, and names are derived exclusively from provided context payloads.
- Anti-repetition: Suppression keys prevent duplicate sends across ticks.

## API Endpoints
The service exposes the official HTTP endpoints under both `/v1/*` and root paths:
- GET `/v1/healthz` — Service health and loaded context counts.
- GET `/v1/metadata` — Bot metadata and implementation details.
- POST `/v1/context` — Idempotent context push endpoint.
- POST `/v1/tick` — Periodic tick handler for active triggers; returns action list.
- POST `/v1/reply` — Multi-turn conversation handler; returns next action (send, wait, or end).

## How to Run Locally

### 1. Prerequisites and Setup
Python 3.9+ is required.

```bash
python3 -m venv venv
./venv/bin/pip install fastapi uvicorn pydantic pytest
```

### 2. Run Dataset Generator
Expands seed data into 50 merchants, 200 customers, 100 triggers, and 30 canonical test pairs:

```bash
./venv/bin/python3 dataset/generate_dataset.py --seed-dir ./dataset --out ./dataset/expanded
```

### 3. Generate Submission File
Generates `submission.jsonl` for the 30 canonical test pairs:

```bash
./venv/bin/python3 generate_submission.py
```

### 4. Run Unit Tests
Runs pytest test suite covering engine logic, versioning, auto-reply, intent transition, and opt-outs:

```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_engine.py
```

### 5. Start HTTP Server
Launches the FastAPI server on port 8088:

```bash
./venv/bin/uvicorn bot:app --host 0.0.0.0 --port 8088
```

### 6. Run Harness Verification & Judge Simulator
Runs local verification harness and judge simulator tests against the running server:

```bash
BOT_URL=http://localhost:8088 ./venv/bin/python3 run_local_test.py
```

To run `judge_simulator.py` with an LLM provider:

```bash
export BOT_URL=http://localhost:8088
export LLM_API_KEY=<YOUR_API_KEY>
./venv/bin/python3 judge_simulator.py
```

## Deployment Instructions
- The service runs as a standard FastAPI application via Uvicorn.
- Deploy to any cloud environment (GCP Cloud Run, AWS ECS, Render, Fly.io, or ngrok tunnel).
- Expose port 8080/8088 over HTTPS/HTTP. No external database or persistent queue is required.

## Key Tradeoffs
- In-memory state: Optimized for maximum speed and simplicity under challenge response limits (<15ms latency). State resets on process restart unless backed by persistent store.
- Pure deterministic composition vs pure LLM: Chosen for 100% stability, sub-20ms response time, zero hallucination risk, and reproducible scoring across judge runs.
