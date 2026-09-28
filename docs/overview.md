What is FDE Support Copilot?

FDE Support Copilot is a Slack bot that drafts answers to support questions using a knowledge base, but never sends anything to a customer without a human clicking Approve first. It watches a support inbox channel for incoming questions, retrieves the most relevant passages from its knowledge base, drafts a grounded answer with sources and a confidence label, then posts that draft privately to a team-only review channel with Approve, Edit, and Reject buttons.

Who built it and why

Built by Karen Ekiyabe as a portfolio project to demonstrate a real third-party integration (the Slack API), a real cloud deployment (Docker on Render), and a human-in-the-loop safety pattern applied to a live external system rather than an internal tool. It reuses the same LangGraph interrupt-and-resume pattern as her other project, ai-data-agent, where a mistake in an internal spreadsheet is low-stakes but a mistake sent to a real customer is not.

What happens if the agent doesn't know the answer

If nothing relevant is found in the knowledge base, the agent explicitly says so in its draft rather than guessing or hallucinating an answer. A human reviewer sees that low-confidence label before deciding whether to approve, edit, or reject the draft.

Where the code lives

The full source is open source at github.com/Nyamey/fde-support-copilot, MIT licensed.
