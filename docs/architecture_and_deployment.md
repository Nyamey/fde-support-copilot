How the agent is deployed

The agent runs in a single Docker container on Render's free-tier Web Service plan. The container runs a Flask app served by gunicorn, which handles two things: a health-check route at the root path that returns "ok", and a POST route at /slack/events that receives every Slack event and interactive-button click.

Why HTTP mode instead of Socket Mode

Slack apps can receive events two ways: Socket Mode (an outbound WebSocket connection, no public URL needed) or HTTP mode (Slack POSTs to a public URL you provide). Render's free tier only offers Web Services, which need a public HTTP port; Background Workers, which would suit Socket Mode better, start at $7/month on Render. So this deployment uses HTTP mode, with request signature verification via SLACK_SIGNING_SECRET.

What powers retrieval

The knowledge base is stored in DuckDB, in the same container, with each passage's text embedding computed through LiteLLM (mistral/mistral-embed by default). Retrieval is a cosine-similarity search over those stored embeddings — no separate vector-database service is needed, which keeps the whole deployment to one container.

What powers the LLM drafting step

Also LiteLLM, with the same multi-provider fallback pattern used in Karen's other portfolio project, ai-data-agent: if one provider is down or out of quota, the agent tries the next one rather than failing outright.

Known limitations of this deployment

Render's free tier spins the container down after a period of inactivity and takes roughly 20-30 seconds to wake back up on the next request ("cold start"). A Slack event arriving during a cold start may time out before the container finishes waking up. This is a known trade-off of the free tier, not a bug in the agent itself — a paid Render plan would remove it.

The Slack workspace this bot is currently installed in is a personal test workspace, not a live customer-facing support channel for an external company.
