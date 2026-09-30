# FDE Support Copilot overview
## What FDE Support Copilot is
FDE Support Copilot is a Slack bot that drafts answers to support questions from a small knowledge base. It watches one support inbox channel. For each new question, it finds the most relevant passages in the knowledge base, drafts an answer from those passages only, and posts the draft in a separate review channel with three buttons: Approve, Edit and Reject. Nothing is posted in the support thread until a reviewer approves or edits the draft.

## Who built it and why
Karen Ekiyabe built it as a portfolio project, to practise three things: an integration with an external tool through the Slack API, a Docker deployment on a cloud host, and a human approval step on a system that other people can see. It reuses the pause-and-resume pattern of her other project, ai-data-agent, where a person approves the analysis plan before the agent goes on. She built it with AI coding assistants and stays responsible for the design choices, the tests and the validation.

## What the knowledge base contains
The knowledge base holds the Markdown files of the docs folder of the repository, plus the answers approved in Slack since the service last started. The docs describe the bot itself: how the approval works, how it is deployed, how it is tested and how to set it up. Anyone can check an answer against these files, and no customer data is involved.

## What happens when the knowledge base has no answer
Every passage gets a similarity score against the question, and passages below the relevance threshold are dropped. When no passage is left, the bot does not call the language model: the draft is a fixed message saying the knowledge base does not have enough information. The reviewer sees "confidence: none" and no sources, and can answer by hand. The model is also told to reply with a fixed marker when the passages it receives do not cover the question, and the bot turns that marker into the same fixed message.

## Current status
The Slack app is installed in a personal test workspace. No company or customer uses the bot.

## Where the code lives
The source code is public on GitHub at github.com/Nyamey/fde-support-copilot, under the MIT licence.
