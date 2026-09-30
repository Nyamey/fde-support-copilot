# Evaluation drafts

Every draft of the last run, as the reviewer would see it.

## q01: What does FDE Support Copilot do?

Answerable from the docs: yes. Confidence: 0.74.

> FDE Support Copilot is a Slack bot that monitors a support inbox channel, finds the most relevant passages in a small knowledge base for each new question, drafts an answer using only those passages, and posts the draft in a separate review channel where it can be approved, edited, or rejected before anything is posted in the original support thread.

## q02: Who built this bot, and why?

Answerable from the docs: yes. Confidence: 0.55.

> Karen Ekiyabe built the bot as a portfolio project to practice three things: integrating with an external tool via the Slack API, deploying a Docker container on a cloud host, and implementing a human-approval step that others can see. She used AI coding assistants for development and remains responsible for the design, tests, and validation.

## q03: Is the bot used by real customers?

Answerable from the docs: yes. Confidence: 0.48.

> No, the bot is only installed in a personal test workspace and is not used by any company or real customers.

## q04: Where can I read the source code?

Answerable from the docs: yes. Confidence: 0.52.

> You can read the source code on GitHub at github.com/Nyamey/fde-support-copilot.

## q05: What does the bot do when the knowledge base has no answer?

Answerable from the docs: yes. Confidence: 0.69.

> When no passage meets the relevance threshold, the bot skips calling the language model and generates a fixed draft that says the knowledge base does not have enough information. The reviewer sees “confidence: none” with no sources and must answer the question manually.

## q06: Is the draft posted in the support channel straight away?

Answerable from the docs: yes. Confidence: 0.53.

> No. The draft is first sent to a separate review channel and is only posted in the support thread after it is approved.

## q07: What does the Edit button do?

Answerable from the docs: yes. Confidence: 0.6.

> The Edit button opens a form that lets the reviewer rewrite the draft; the rewritten answer is then posted in the thread and added to the knowledge base instead of the original draft.

## q08: What happens when a reviewer clicks Reject?

Answerable from the docs: yes. Confidence: 0.7.

> When a reviewer clicks Reject, the run ends. No answer is posted in the support thread and nothing is added to the knowledge base. The reviewer can then provide an answer manually.

## q09: Who is allowed to approve an answer?

Answerable from the docs: yes. Confidence: 0.53.

> Any member of the review channel can approve an answer.

## q10: What does the confidence label mean?

Answerable from the docs: yes. Confidence: 0.66.

> The confidence label is based on the highest similarity score of the passages used for the draft. It shows “high” when the score is 0.5 or above, “low” when it is below 0.5, and “none” when no passage meets the relevance threshold or the model determines the passages don’t cover the question. It indicates how closely the passages match the question, not the probability that the answer is correct, so reviewers should still verify the sources.

## q11: What happens if two reviewers click Approve on the same question?

Answerable from the docs: yes. Confidence: 0.58.

> The first reviewer’s Approve is recorded, the review message is replaced with the decision and the buttons disappear. Any later click—whether by the same reviewer or another reviewer on the same question—does nothing; it does not restart the run or change the decision, and the second reviewer receives a private note that the question is no longer waiting for review.

## q12: Does a reply inside a thread count as a new question?

Answerable from the docs: yes. Confidence: 0.56.

> No, a reply inside a thread is ignored and does not start a new question.

## q13: Where is the approved answer posted?

Answerable from the docs: yes. Confidence: 0.55.

> The approved answer is posted as a reply in the original thread of the support inbox.

## q14: Where is the bot hosted?

Answerable from the docs: yes. Confidence: 0.65.

> The bot is hosted on Render, running in a single Docker container on the free plan as a Web Service at fde-support-copilot.onrender.com.

## q15: Why does the deployment use HTTP mode rather than Socket Mode?

Answerable from the docs: yes. Confidence: 0.6.

> The deployment uses HTTP mode because Render’s free plan only provides Web Services that require a public HTTP endpoint. Using Socket Mode would need background workers, which start at $7 per month on Render. Therefore, the app runs in HTTP mode, with Slack Bolt verifying each request’s signature via the signing secret. Socket Mode is kept only for local development.

## q16: How long does the service take to wake up after it goes to sleep?

Answerable from the docs: yes. Confidence: 0.59.

> The wake-up can take about a minute or more – roughly 80 seconds in a recent test.

## q17: Why could Slack send the same question twice?

Answerable from the docs: yes. Confidence: 0.58.

> Slack may resend the same question when the service has been sleeping. On the free plan the app goes to sleep after 15 minutes of inactivity; the first request that wakes it can take a minute or more, causing Slack’s 3-second reply timeout. When that timeout occurs, Slack retries the event, so the same question is sent again.

## q18: What is lost when the service restarts?

Answerable from the docs: yes. Confidence: 0.63.

> When the service restarts, any runs that were waiting for review and any answers that were added to the knowledge base since the last start are lost.

## q19: Which embedding model does retrieval use?

Answerable from the docs: yes. Confidence: 0.57.

> Retrieval uses embeddings computed with the openai/text-embedding-3-small model via LiteLLM on OpenRouter.

## q20: Which language model writes the drafts?

Answerable from the docs: yes. Confidence: 0.76.

> The drafts are generated by the model set in SUPPORT_COPILOT_LLM_MODEL, which by default is openai/gpt-oss-120b running on Groq (called through LiteLLM with a temperature of 0.2).

## q21: What happens if the language model provider is down?

Answerable from the docs: yes. Confidence: 0.58.

> If the provider is down, the system tries backup models listed in SUPPORT_COPILOT_LLM_FALLBACKS. If all models fail, the review channel receives a message that no draft could be produced (including the question), so the team must answer manually.

## q22: How many automated tests does the project have?

Answerable from the docs: yes. Confidence: 0.56.

> The project has 45 automated tests.

## q23: Do the tests call the real Slack API?

Answerable from the docs: yes. Confidence: 0.72.

> No. The tests use test doubles for Slack, so they never call the real Slack API.

## q24: How was the relevance threshold chosen?

Answerable from the docs: yes. Confidence: 0.72.

> The relevance threshold was determined by evaluating an evaluation set of 40 questions (30 that the docs can answer and 10 that they cannot). The script recorded the best similarity score for each question and compared the score distributions of the two groups. The threshold was set to reject off-topic questions while retaining those the documentation can answer. This resulted in the default value of 0.33 (SUPPORT_COPILOT_MIN_RELEVANCE), which may be re-measured if the embedding model changes.

## q25: What are the limits of the evaluation?

Answerable from the docs: yes. Confidence: 0.47.

> The evaluation is limited because the questions were written with the documentation in view, making them easier than real-world queries. It uses a very small knowledge base of only five files, and the key-fact check only looks for a specific word rather than verifying a complete, correct answer. Consequently, the results may not reflect performance on typical team questions.

## q26: Which Slack permissions does the bot need?

Answerable from the docs: yes. Confidence: 0.74.

> The bot requires three Slack scopes: chat:write, channels:history, and channels:read. (If you use a private support inbox you’ll also need the groups:history scope and the message.groups event.)

## q27: How do I add new documents to the knowledge base?

Answerable from the docs: yes. Confidence: 0.67.

> Put the new Markdown or text files into the docs folder, then run the ingest command again. This will split the files into passages and update the knowledge base, replacing any passages from the files it reads while preserving approved Slack answers.

## q28: Qui peut valider une réponse ?

Answerable from the docs: yes. Confidence: 0.39.

> Tout membre du canal de révision peut valider une réponse.

## q29: Où le bot est-il hébergé ?

Answerable from the docs: yes. Confidence: 0.57.

> Le bot est hébergé sur Render, dans un conteneur Docker sur le plan gratuit, accessible via le service web fde-support-copilot.onrender.com.

## q30: Comment ajouter des documents à la base de connaissances ?

Answerable from the docs: yes. Confidence: 0.6.

> Placez vos fichiers Markdown ou texte dans le dossier docs, puis relancez la commande d’ingestion. Cette opération découpe les fichiers en passages et met à jour la base de connaissances. (Un titre placé directement au-dessus d’un paragraphe, sans ligne vide, reste dans le même passage.)

## o01: What is the capital of Peru?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o02: Can you recommend a good pasta recipe?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o03: Who won the 2022 football World Cup?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o04: What is the euro to dollar exchange rate today?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o05: How much does the enterprise plan cost per user?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o06: How do I reset my password?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o07: What is your refund policy?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o08: How do I export my invoices to Excel?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o09: What are your phone support hours?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

## o10: Comment supprimer mon compte et toutes mes données ?

Answerable from the docs: no. Confidence: 0.0.

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?

Same question with all five passages, threshold switched off:

> I don't have enough information in the knowledge base to answer this confidently. Could you check with the team?
