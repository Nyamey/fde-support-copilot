# Testing and quality
## The automated tests
The repository has 45 automated tests, run with pytest. They cover each agent step on its own, the relevance threshold, the backup models, the refusal marker, the ingestion and search of the knowledge base, the Slack handlers, the guard against duplicate Slack events, and two runs through the real LangGraph graph and its SQLite checkpoint: one approved, one rejected.

## Do the tests call real services
No. Slack, the language model and the embedding API are replaced by test doubles, so the tests never call a real service and need no API key. The evaluation set is the part that calls the real models.

## Continuous integration
GitHub Actions runs the whole test suite with Python 3.12 on every push and every pull request. An early CI run failed because plain pytest did not add the repository root to the import path; the fix was a pythonpath setting in pyproject.toml.

## The evaluation set
The evaluation folder holds 40 questions: 30 that the docs answer, each with the file that should be retrieved and a key fact the answer should contain, and 10 that the docs do not answer. A script rebuilds the knowledge base from the docs in a temporary database and runs every question through retrieval and drafting with the real models. It measures whether the right file is among the five passages retrieved and in first place, whether the off-topic questions are refused, whether the answers contain the key fact, and how long each step takes. The results are in evaluation/results and in the README.

## How the relevance threshold was chosen
The evaluation script records the best similarity score of every question. The threshold was chosen to refuse the off-topic questions while keeping the questions the docs answer, by comparing the two groups of scores. The script prints a table with the result of each candidate threshold.

## What the evaluation does not show
The questions were written with the docs in view, so they are probably easier than real ones. The knowledge base is small, with five files. The key-fact check looks for a word, not for a correct and complete answer, so the drafts are saved with the results to be read. Questions from a real team would be a better test.
