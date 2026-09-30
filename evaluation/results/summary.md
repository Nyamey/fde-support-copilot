# Evaluation results

Run on 2026-09-30 with the 40 questions of evaluation/questions.csv: 30 answerable from docs/ (3 in French) and 10 off-topic.
Knowledge base: 39 passages from docs/. Embedding model: `openrouter/openai/text-embedding-3-small`. Drafting model: `groq/openai/gpt-oss-120b`. Relevance threshold: 0.33.

## Summary

| Measure | Result |
|---|---|
| Right file among the 5 passages retrieved | 30/30 |
| Right file in first place | 30/30 |
| Answerable questions with a passage above the threshold | 30/30 |
| Off-topic questions refused before any model call | 10/10 |
| Answerable questions answered, not refused | 30/30 |
| Answers containing the key fact | 27/30 |
| Off-topic questions refused, by the threshold or by the model | 10/10 |
| Off-topic questions refused by the model alone, threshold switched off | 10/10 |
| Retrieval time per question, embedding call included | median 0.46 s, max 0.99 s |
| Drafting time when the model is called | median 0.53 s, max 1.40 s |
| Waits for the provider's rate limit, not counted in the times | 1 |

## Candidate thresholds

Best similarity score of each question compared with the threshold, before any model call.

| Threshold | Answerable questions kept (of 30) | Kept with the right file (of 30) | Off-topic questions refused (of 10) |
|---|---|---|---|
| 0.20 | 30 | 30 | 7 |
| 0.25 | 30 | 30 | 8 |
| 0.30 | 30 | 30 | 10 |
| 0.33 | 30 | 30 | 10 |
| 0.35 | 30 | 30 | 10 |
| 0.40 | 29 | 29 | 10 |
| 0.45 | 29 | 29 | 10 |
| 0.50 | 27 | 27 | 10 |
| 0.55 | 23 | 23 | 10 |
| 0.60 | 13 | 13 | 10 |

## Best score per question

| Id | Language | Answerable | Best score | Best file | Right file in top 5 | Refused | Key fact |
|---|---|---|---|---|---|---|---|
| q20 | en | yes | 0.762 | architecture_and_deployment.md | yes | no | yes |
| q26 | en | yes | 0.743 | setup.md | yes | no | yes |
| q01 | en | yes | 0.737 | overview.md | yes | no | yes |
| q23 | en | yes | 0.723 | testing_and_quality.md | yes | no | yes |
| q24 | en | yes | 0.720 | testing_and_quality.md | yes | no | yes |
| q08 | en | yes | 0.704 | approval_flow.md | yes | no | no |
| q05 | en | yes | 0.690 | overview.md | yes | no | yes |
| q27 | en | yes | 0.665 | setup.md | yes | no | yes |
| q10 | en | yes | 0.662 | approval_flow.md | yes | no | yes |
| q14 | en | yes | 0.652 | architecture_and_deployment.md | yes | no | yes |
| q18 | en | yes | 0.626 | architecture_and_deployment.md | yes | no | yes |
| q30 | fr | yes | 0.604 | setup.md | yes | no | yes |
| q07 | en | yes | 0.601 | approval_flow.md | yes | no | yes |
| q15 | en | yes | 0.599 | architecture_and_deployment.md | yes | no | yes |
| q16 | en | yes | 0.589 | architecture_and_deployment.md | yes | no | yes |
| q17 | en | yes | 0.579 | architecture_and_deployment.md | yes | no | no |
| q11 | en | yes | 0.579 | approval_flow.md | yes | no | no |
| q21 | en | yes | 0.575 | architecture_and_deployment.md | yes | no | yes |
| q29 | fr | yes | 0.572 | architecture_and_deployment.md | yes | no | yes |
| q19 | en | yes | 0.572 | architecture_and_deployment.md | yes | no | yes |
| q22 | en | yes | 0.561 | testing_and_quality.md | yes | no | yes |
| q12 | en | yes | 0.558 | approval_flow.md | yes | no | yes |
| q13 | en | yes | 0.554 | approval_flow.md | yes | no | yes |
| q02 | en | yes | 0.547 | overview.md | yes | no | yes |
| q09 | en | yes | 0.533 | approval_flow.md | yes | no | yes |
| q06 | en | yes | 0.526 | approval_flow.md | yes | no | yes |
| q04 | en | yes | 0.518 | overview.md | yes | no | yes |
| q03 | en | yes | 0.483 | overview.md | yes | no | yes |
| q25 | en | yes | 0.467 | testing_and_quality.md | yes | no | yes |
| q28 | fr | yes | 0.387 | approval_flow.md | yes | no | yes |
| o07 | en | no | 0.279 | approval_flow.md |  | yes |  |
| o09 | en | no | 0.252 | overview.md |  | yes |  |
| o05 | en | no | 0.222 | architecture_and_deployment.md |  | yes |  |
| o06 | en | no | 0.196 | approval_flow.md |  | yes |  |
| o08 | en | no | 0.182 | setup.md |  | yes |  |
| o10 | fr | no | 0.168 | approval_flow.md |  | yes |  |
| o02 | en | no | 0.112 | overview.md |  | yes |  |
| o03 | en | no | 0.109 | architecture_and_deployment.md |  | yes |  |
| o04 | en | no | 0.100 | overview.md |  | yes |  |
| o01 | en | no | 0.098 | approval_flow.md |  | yes |  |
