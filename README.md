# FDE Support Copilot

**A human-approved AI agent that drafts support answers inside a real Slack workspace, grounded in the team's own knowledge base — and never sends anything to a customer without a human clicking "approve" first.**

Live case study · [ai-data-agent](https://github.com/Nyamey/ai-data-agent) · [opc-rpa-ia-reporting](https://github.com/Nyamey/opc-rpa-ia-reporting)

---

## The problem

A small support or customer-success team gets repetitive questions in a Slack channel (or a shared inbox forwarded to Slack). Every answer requires someone to re-find the same three paragraphs in the docs, rephrase them, and reply — five minutes of low-value work, dozens of times a day. The team wants speed without losing control over what actually gets sent to a customer.

## What this agent does

1. **Watches** a Slack channel for incoming questions (`app_mention` or a dedicated `#support-inbox` channel).
2. **Retrieves** the most relevant passages from the team's knowledge base (docs, past resolved tickets, FAQ) using a local vector store.
3. **Drafts** a grounded answer with the sources it used, and a confidence label.
4. **Stops and asks a human** — the draft is posted as a private thread reply visible only to the support team, with Approve / Edit / Reject buttons. Nothing reaches the customer until a person clicks Approve.
5. **Posts** the approved (or edited) answer publicly, and logs the exchange for future retrieval — the knowledge base gets better every time a human corrects the agent.

This is the same human-in-the-loop discipline already proven in [ai-data-agent](https://github.com/Nyamey/ai-data-agent) (`interrupt_before` checkpoint, replayable audit log), applied here to a live external system where a mistake is visible to a real customer instead of an internal spreadsheet — a deliberately higher-stakes environment.

## Why this project exists

Built to close three specific gaps between my first two portfolio projects and what Forward Deployed / Solutions Engineer hiring managers actually screen for in 2026:

| Gap identified | How this project closes it |
|---|---|
| No integration with a live third-party API/system | Real Slack API (OAuth, Events API or Socket Mode, Block Kit interactive buttons) — not a local-only demo |
| No cloud/containerized deployment | Dockerized, deployed to a free-tier cloud host (Render/Fly.io), reachable 24/7 |
| No "deployed for a real external user" story | Designed to run in an actual small Slack workspace (a friend's startup, an open-source community, a volunteer org) rather than a synthetic dataset |
| No client-facing narrative in prior write-ups | This README, and the eventual demo video, are written as a case study — problem, decision, trade-off, outcome — not an engineering changelog |

## Architecture

```
Slack event (question posted)
        │
        ▼
  ┌─────────────┐
  │  retrieve   │  vector search over knowledge_base/ (DuckDB VSS or Chroma)
  └─────┬───────┘
        ▼
  ┌─────────────┐
  │    draft    │  LLM drafts an answer + cites sources + confidence score
  └─────┬───────┘
        ▼
  ┌─────────────┐
  │ human_gate  │  LangGraph interrupt_before — posted to team-only thread,
  │             │  Approve / Edit / Reject via Slack Block Kit buttons
  └─────┬───────┘
        ▼
  ┌─────────────┐
  │    post     │  approved answer goes to the public channel
  └─────┬───────┘
        ▼
  ┌─────────────┐
  │    log      │  exchange appended to knowledge_base/ for future retrieval
  └─────────────┘
```

Same orchestration pattern as `ai-data-agent` (LangGraph, persistent checkpointed state, a real interrupt rather than a fake confirmation dialog), pointed at a live external system instead of an internal one.

## Stack

- **Orchestration:** LangGraph (persistent state, `interrupt_before` for the human gate)
- **Slack integration:** `slack-bolt` (Socket Mode for local dev, switchable to HTTP + signed requests for the cloud deployment)
- **Retrieval:** DuckDB (reusing the same engine as `ai-data-agent`) with a vector-search extension, or Chroma if DuckDB VSS proves too limited for embeddings at this scale
- **LLM:** LiteLLM (same multi-provider fallback pattern as the other two projects — one provider down doesn't take the agent down)
- **Deployment:** Docker on Render's free-tier Web Service — HTTP mode (Flask + gunicorn, `SLACK_MODE=http`) rather than Socket Mode, since Render's free tier is Web Services only (Background Workers, the natural fit for Socket Mode, start at $7/mo)
- **Tests:** pytest, targeting the same rigor bar as the other two projects (agent nodes tested in isolation, Slack event parsing tested without hitting the real API)

## Status

Implemented and tested (26 tests, 93% coverage on `agent/` and `knowledge_base/`). Retrieval uses cosine similarity over DuckDB-stored embeddings computed through LiteLLM (`mistral/mistral-embed` by default), so no dedicated vector-database service or extra ML dependency is needed in the container. The draft node explicitly refuses to answer when nothing relevant was retrieved, rather than letting the LLM guess. The Slack review flow (Approve / Edit-then-resume / Reject) is fully wired through LangGraph's `interrupt_before` + `update_state`/`invoke(None, ...)` resume pattern, over either Socket Mode (local dev) or HTTP mode (`SLACK_MODE=http`, for the Render deployment — Render's free tier is Web Services only, which need a public port; Background Workers, the natural fit for Socket Mode, start at $7/mo).

A Slack app exists (manifest at `slack-app-manifest.yml`, imported via api.slack.com/apps), installed to a personal test workspace with Socket Mode + an app-level token generated. **Not done yet:** the Render Web Service itself, and pointing the Slack app's Event Subscriptions / Interactivity Request URL at it (needs the Render URL first, then Slack verifies it's reachable) — see `.env.example` for every secret the deployment needs, none of which are committed here on purpose.

## Project layout

```
fde-support-copilot/
├── agent/
│   ├── graph.py          # LangGraph state machine: retrieve → draft → human_gate → post → log
│   ├── nodes.py          # individual node implementations
│   └── state.py          # the shared agent state (Pydantic model)
├── knowledge_base/
│   ├── db.py             # shared DuckDB connection + LiteLLM embedding helper
│   ├── ingest.py         # chunks docs/tickets and loads them into the vector store
│   └── retriever.py      # cosine-similarity search used by the retrieve node
├── slack_app.py          # Slack Bolt app: event listeners + Block Kit approve/edit/reject buttons
├── tests/
│   ├── test_agent_nodes.py
│   └── test_slack_events.py
├── Dockerfile
├── docker-compose.yml    # local dev: app + any local vector store service
├── .github/workflows/ci.yml
├── requirements.txt
└── .env.example
```

## Running locally

```bash
cp .env.example .env        # fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, an LLM API key
pip install -r requirements.txt
python knowledge_base/ingest.py --source ./docs   # index a starter knowledge base
python slack_app.py                                # SLACK_MODE=socket (default) — no public URL needed
```

## Running in HTTP mode (what the Render deployment uses)

```bash
SLACK_MODE=http gunicorn -b 0.0.0.0:3000 slack_app:flask_app
```

Needs `SLACK_SIGNING_SECRET` set and a public URL (Render assigns one) pointed at from both **Event Subscriptions** and **Interactivity & Shortcuts** in the Slack app config, request URL `https://<your-service>.onrender.com/slack/events` for both.
