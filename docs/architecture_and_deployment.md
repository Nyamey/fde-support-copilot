# Architecture and deployment
## The steps of the agent
The agent is a LangGraph state machine with five steps: retrieve, draft, human_gate, post and log. It pauses before human_gate until a reviewer decides. After a rejection the run ends; after an approval or an edit it continues to post and log.

## Where the bot is hosted
The bot is hosted on Render, in one Docker container on the free plan, as a Web Service at fde-support-copilot.onrender.com. Inside the container, gunicorn serves a small Flask app with two routes: the root path returns "ok" for health checks, and POST /slack/events receives every Slack event and every button click.

## Why HTTP mode rather than Socket Mode
Slack can deliver events over Socket Mode, a WebSocket that the app opens, or over HTTP, where Slack sends requests to a public URL. Render's free plan only offers Web Services, which need a public HTTP port. Background workers, the natural fit for Socket Mode, start at 7 dollars a month on Render. So the deployment uses HTTP mode, and Slack Bolt checks the signature of every request with the signing secret. Socket Mode stays available for local development.

## Sleeping and waking up
The free plan puts the service to sleep after 15 minutes without incoming traffic. The next request wakes it up, which can take a minute or more: 80 seconds in a check on 30 September 2026. The container also rebuilds the knowledge base when it starts. Slack expects a reply within 3 seconds, so the first question after a sleep often times out on Slack's side, and Slack sends the same event again.

## How duplicate Slack events are handled
Each run is keyed by the channel and the timestamp of the original Slack message. When Slack sends the same event again, the bot sees that a run for that message is already in progress or already has a draft, and skips it. One question gives one review message, even after a slow start.

## What is lost when the service restarts
The free plan has no persistent disk. When the service sleeps or restarts, the runs waiting for review and the answers added to the knowledge base since the last start are lost. A question should therefore be reviewed before the service goes to sleep. If a reviewer clicks a button on a question that is no longer saved, the bot sends a private note asking them to answer by hand. A paid instance that does not sleep, with a persistent disk, would remove this limit.

## How retrieval works
The knowledge base is stored in DuckDB inside the container. Each passage has an embedding computed through LiteLLM with the openai/text-embedding-3-small model on OpenRouter. For each question, the bot computes the cosine similarity between the question and every passage, keeps the five best, then drops those below the relevance threshold. No separate vector database is needed at this size.

## The relevance threshold
The relevance threshold is set by SUPPORT_COPILOT_MIN_RELEVANCE, with a default of 0.33. It was chosen with an evaluation set of 40 questions, kept in the evaluation folder of the repository: 30 questions that the docs answer and 10 that they do not. Similarity scales differ between embedding models, so the threshold has to be measured again after a change of embedding model.

## Which language model writes the drafts
The drafts are written by the model named in SUPPORT_COPILOT_LLM_MODEL, by default openai/gpt-oss-120b on Groq, called through LiteLLM with a temperature of 0.2. The prompt tells the model to answer only from the passages, and to reply with a fixed marker when they do not cover the question.

## What happens when the model provider fails
SUPPORT_COPILOT_LLM_FALLBACKS can list backup models, tried in order when a call fails, for example when a provider is down, a quota is reached or a model is retired. If every model fails, the review channel gets a message saying that no draft could be produced, with the question, so the team can answer by hand.

## Where the secrets live
No secret is stored in the repository. The Slack bot token, the signing secret, the channel IDs and the provider API keys are environment variables set on Render. The file .env.example lists every variable the deployment needs.
