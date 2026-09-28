How this project is tested

The project has an automated pytest suite covering both the agent's decision logic and the Slack integration, targeting the same rigor bar as Karen's other portfolio projects: agent nodes are tested in isolation, and Slack event parsing is tested without ever hitting Slack's real API. As of the last recorded run, coverage sits at 93% across the agent and knowledge_base modules.

What happens when nothing relevant is in the knowledge base

The retrieve step is designed to fail safely: if no passage in the knowledge base is relevant enough to the question, the draft step does not invent an answer. It returns a response that says so explicitly, with a low-confidence label, so a human reviewer knows immediately that this one needs their own judgment rather than a rubber-stamp approval.

Continuous integration

Every push and pull request runs the full test suite through GitHub Actions. A previous CI run failed the first time because the workflow invoked pytest directly rather than through python -m pytest, which does not add the project root to the import path by default; the fix was adding a pythonpath setting to pyproject.toml so the plain pytest entry point resolves top-level imports correctly regardless of how it's invoked.
