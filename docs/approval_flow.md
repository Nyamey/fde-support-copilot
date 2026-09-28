How the human-approval flow works

When a question is posted in the support inbox channel, the agent runs through four steps before a human ever sees it: retrieve relevant passages from the knowledge base, draft an answer grounded in those passages, attach a confidence label, and stop. The draft is never posted to the customer-facing channel at this point.

Instead, the draft is posted to a separate, team-only review channel as a private message with three buttons: Approve, Edit, and Reject.

What each button does

Approve sends the draft exactly as written to the original customer-facing channel, and logs the exchange as-is.

Edit opens a modal where a reviewer can rewrite the answer before it goes out. The edited version is what gets sent and logged, not the original draft.

Reject stops the process entirely. Nothing is sent to the customer, and the interaction is not logged as a resolved answer.

Why this matters technically

This is implemented as a real LangGraph interrupt_before checkpoint, not a confirmation dialog bolted on afterward. The agent's execution genuinely pauses and persists its state; the Approve/Edit/Reject action resumes the same paused execution rather than starting a new one. This means a reviewer can take their time — minutes or hours — before responding, and the agent picks up exactly where it left off.

Who can approve

Any member of the team-review Slack channel can click Approve, Edit, or Reject. The reviewer's Slack user ID is recorded alongside the final answer for accountability.
