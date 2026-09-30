# How the approval flow works
## The steps before a person sees the draft
When someone posts a new message in the support inbox channel, the bot retrieves the most relevant passages from the knowledge base, drops the passages below the relevance threshold, drafts an answer from the passages that are left, and then stops. The draft is never posted in the support inbox at this point.

## What the review message shows
The draft goes to a separate review channel. The review message shows the question, the draft answer, a confidence label, and the source files behind the draft with their similarity scores, followed by three buttons: Approve, Edit and Reject.

## What the confidence label means
The confidence label comes from the best similarity score among the passages used for the draft. It reads "high" from 0.5, "low" below that, and "none" when no passage passed the relevance threshold or when the model said the passages do not cover the question. It measures how close the passages are to the question. It is not the probability that the answer is correct, so the reviewer should still check the sources.

## What Approve does
Approve posts the draft exactly as written as a reply in the original thread of the support inbox. The bot then adds the question and the answer to the knowledge base, so that a similar question can find them later.

## What Edit does
Edit opens a form where the reviewer can rewrite the draft. The rewritten answer is the one posted in the thread and added to the knowledge base, not the original draft.

## What Reject does
Reject ends the run. Nothing is posted in the support thread and nothing is added to the knowledge base. The reviewer can then answer by hand.

## Why the pause is a real pause
The pause is a LangGraph interrupt placed before the human_gate step. The run stops and its state is saved in a SQLite checkpoint, keyed by the Slack channel and the timestamp of the question. A button click resumes that same saved run with the reviewer's decision. The only path to posting an answer goes through this step.

## Who can approve
Any member of the review channel can click Approve, Edit or Reject. The reviewer's Slack user ID is saved with the decision in the state of the run.

## What happens after a decision
The review message is replaced by the decision and the name of the reviewer, so the buttons disappear. A decision counts once: a second click, or a click by another reviewer on the same question, does not resume the run again and does not change the recorded decision. The person who clicked gets a private note saying the question is no longer waiting for review.

## Which messages count as questions
Only new top-level messages in the support inbox channel start a run. Edited or deleted messages, replies inside a thread and the bot's own messages are ignored, so a follow-up question has to be posted as a new message.
