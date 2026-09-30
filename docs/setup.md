# Setting up the bot
## What you need
You need a Slack workspace where you can install apps, two channels (a support inbox and a review channel), an OpenRouter API key for the embeddings, a Groq API key for the drafts, and Python 3.12 or Docker.

## Creating the Slack app
Create the app at api.slack.com/apps from a manifest. For local development, use slack-app-manifest.yml, which turns Socket Mode on. For the Render deployment, use slack-app-manifest.http.yml, which turns Socket Mode off and sends events and button clicks to https://fde-support-copilot.onrender.com/slack/events. Install the app in the workspace, then invite the bot to both channels. The channel ID is at the bottom of the channel details in Slack.

## Slack permissions
The bot asks for three scopes: chat:write to post the review message and the answer, channels:history to receive the messages of a public support inbox, and channels:read. It listens to the message.channels event. A private support inbox would also need the groups:history scope and the message.groups event.

## Environment variables
The bot needs SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET, plus SLACK_APP_TOKEN in Socket Mode only; SLACK_MODE, set to socket or http; SUPPORT_INBOX_CHANNEL_ID and TEAM_REVIEW_CHANNEL_ID; OPENROUTER_API_KEY and EMBEDDING_MODEL for the embeddings; GROQ_API_KEY and SUPPORT_COPILOT_LLM_MODEL for the drafts. SUPPORT_COPILOT_LLM_FALLBACKS and SUPPORT_COPILOT_MIN_RELEVANCE are optional. The file .env.example lists them all with comments.

## Running the bot on your own computer
Copy .env.example to .env and fill it in, install the requirements, build the knowledge base with python -m knowledge_base.ingest --source ./docs, then start the bot with python slack_app.py. Socket Mode is the default, so no public URL is needed.

## Adding documents to the knowledge base
Put Markdown or text files in the docs folder and run the ingest command again. Each file is cut into passages at blank lines, with at most 1000 characters per passage. Running the ingest again replaces the passages of the files it reads and keeps the answers approved in Slack. A heading written directly above its paragraph, without a blank line, stays in the same passage, which helps retrieval.
