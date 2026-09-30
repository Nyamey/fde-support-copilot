"""Runs the evaluation set against a fresh copy of the knowledge base.

Usage, from the repository root, with the provider keys of EMBEDDING_MODEL
and SUPPORT_COPILOT_LLM_MODEL set (OPENROUTER_API_KEY and GROQ_API_KEY for
the defaults):
    python -m evaluation.run_eval                    # retrieval and drafting
    python -m evaluation.run_eval --retrieval-only   # no drafting calls
    python -m evaluation.run_eval --threshold 0.3    # try another threshold

The knowledge base is rebuilt from docs/ in a temporary DuckDB file, so
knowledge_base/kb.duckdb is never touched. For each question in
evaluation/questions.csv, the script records the five passages retrieved,
then applies the relevance threshold and drafts an answer with the real
model, through the same functions the Slack flow uses. Only the main model
is used, so every draft comes from the model named in the summary.

Writes evaluation/results/results.csv (one row per question),
evaluation/results/drafts.md (every draft, to be read) and
evaluation/results/summary.md (the tables quoted in the README).
"""

import argparse
import csv
import statistics
import tempfile
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Before the project imports: agent.nodes and knowledge_base.db read the
# model names from the environment when they are imported.
load_dotenv()

import litellm  # noqa: E402

from agent import nodes  # noqa: E402
from agent.state import AgentState  # noqa: E402
from knowledge_base import db, ingest, retriever  # noqa: E402

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
DOCS_DIR = EVAL_DIR.parent / "docs"
CANDIDATE_THRESHOLDS = [round(0.20 + 0.05 * i, 2) for i in range(9)]  # 0.20 to 0.60
RATE_LIMIT_RETRIES = 3


def load_questions(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def expected_files(question: dict) -> set[str]:
    return {name for name in question["expected_sources"].split("|") if name}


def contains_key_fact(answer: str, question: dict) -> bool:
    answer = answer.lower()
    return any(fact.lower() in answer for fact in question["key_fact"].split("|") if fact)


def retrieve_all(questions: list[dict]) -> list[dict]:
    runs = []
    for question in questions:
        start = time.perf_counter()
        passages = retriever.search(question["question"], top_k=5)
        runs.append({"question": question, "passages": passages, "retrieve_seconds": time.perf_counter() - start})
    return runs


def timed_draft(question: dict, passages: list) -> tuple[dict, float, int]:
    """nodes.draft, waiting and trying again when the provider's rate limit
    is reached, so a free-tier quota doesn't count as a wrong answer. Returns
    the result, the duration of the call that succeeded (waits excluded) and
    the number of waits.
    """
    state = AgentState(
        question=question["question"],
        slack_channel_id="evaluation",
        slack_thread_ts=question["id"],
        asked_by_user_id="evaluation",
        passages=passages,
    )
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        start = time.perf_counter()
        try:
            return nodes.draft(state), time.perf_counter() - start, attempt
        except litellm.RateLimitError:
            if attempt == RATE_LIMIT_RETRIES:
                raise
            time.sleep(20 * (attempt + 1))


def draft_all(runs: list[dict], threshold: float, pause_seconds: float) -> None:
    for run in runs:
        question = run["question"]
        kept = [p for p in run["passages"] if p.score >= threshold]
        result, seconds, waits = timed_draft(question, kept)
        run.update(
            draft=result["draft_answer"],
            confidence=result["confidence"],
            refused=result["draft_answer"] == nodes.I_DONT_KNOW_FALLBACK,
            draft_seconds=seconds,
            called_model=bool(kept),
            rate_limit_waits=waits,
        )
        if kept:
            time.sleep(pause_seconds)
        if question["answerable"] == "no":
            # Second barrier: the same off-topic question with all five
            # passages, as if the threshold were switched off. Does the model
            # refuse on its own?
            result, _seconds, waits = timed_draft(question, run["passages"])
            run["model_alone_draft"] = result["draft_answer"]
            run["model_alone_refused"] = result["draft_answer"] == nodes.I_DONT_KNOW_FALLBACK
            run["rate_limit_waits"] += waits
            time.sleep(pause_seconds)


def best_score(run: dict) -> float:
    return run["passages"][0].score if run["passages"] else 0.0


def right_file_in(passages: list, question: dict) -> bool:
    return any(p.source in expected_files(question) for p in passages)


def threshold_rows(runs: list[dict], chosen: float) -> list[tuple]:
    answerable = [r for r in runs if r["question"]["answerable"] == "yes"]
    off_topic = [r for r in runs if r["question"]["answerable"] == "no"]
    rows = []
    for threshold in sorted({*CANDIDATE_THRESHOLDS, chosen}):
        kept = sum(best_score(r) >= threshold for r in answerable)
        kept_right = sum(
            right_file_in([p for p in r["passages"] if p.score >= threshold], r["question"]) for r in answerable
        )
        refused = sum(best_score(r) < threshold for r in off_topic)
        rows.append((threshold, kept, kept_right, refused))
    return rows


def seconds_summary(values: list[float]) -> str:
    if not values:
        return "not measured"
    return f"median {statistics.median(values):.2f} s, max {max(values):.2f} s"


def write_results(runs: list[dict], threshold: float, chunk_count: int, drafted: bool) -> str:
    RESULTS_DIR.mkdir(exist_ok=True)
    answerable = [r for r in runs if r["question"]["answerable"] == "yes"]
    off_topic = [r for r in runs if r["question"]["answerable"] == "no"]
    n_ans, n_off = len(answerable), len(off_topic)

    with (RESULTS_DIR / "results.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["id", "lang", "answerable", "question", "expected_sources", "best_file", "best_score",
             "top5", "right_file_top5", "right_file_first", "refused", "key_fact_found", "confidence",
             "retrieve_seconds", "draft_seconds"]
        )
        for r in runs:
            q, passages = r["question"], r["passages"]
            answerable_q = q["answerable"] == "yes"
            writer.writerow([
                q["id"], q["lang"], q["answerable"], q["question"], q["expected_sources"],
                passages[0].source if passages else "", f"{best_score(r):.3f}",
                "; ".join(f"{p.source} {p.score:.3f}" for p in passages),
                right_file_in(passages, q) if answerable_q else "",
                (bool(passages) and passages[0].source in expected_files(q)) if answerable_q else "",
                r.get("refused", ""),
                contains_key_fact(r["draft"], q) if drafted and answerable_q else "",
                r.get("confidence", ""),
                f"{r['retrieve_seconds']:.2f}",
                f"{r['draft_seconds']:.2f}" if drafted else "",
            ])

    if drafted:
        with (RESULTS_DIR / "drafts.md").open("w", encoding="utf-8", newline="\n") as f:
            f.write("# Evaluation drafts\n\nEvery draft of the last run, as the reviewer would see it.\n")
            for r in runs:
                q = r["question"]
                f.write(f"\n## {q['id']}: {q['question']}\n\n")
                f.write(f"Answerable from the docs: {q['answerable']}. Confidence: {r['confidence']}.\n\n")
                f.write("> " + r["draft"].replace("\n", "\n> ") + "\n")
                if "model_alone_draft" in r:
                    f.write("\nSame question with all five passages, threshold switched off:\n\n")
                    f.write("> " + r["model_alone_draft"].replace("\n", "\n> ") + "\n")

    lines = [
        "# Evaluation results",
        "",
        f"Run on {date.today().isoformat()} with the {len(runs)} questions of evaluation/questions.csv: "
        f"{n_ans} answerable from docs/ ({sum(r['question']['lang'] == 'fr' for r in answerable)} in French) "
        f"and {n_off} off-topic.",
        f"Knowledge base: {chunk_count} passages from docs/. Embedding model: `{db.EMBEDDING_MODEL}`. "
        f"Drafting model: `{nodes.LLM_MODEL}`" + (" (not called in this run)." if not drafted else ".")
        + f" Relevance threshold: {threshold}.",
        "",
        "## Summary",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Right file among the 5 passages retrieved | {sum(right_file_in(r['passages'], r['question']) for r in answerable)}/{n_ans} |",
        f"| Right file in first place | {sum(bool(r['passages']) and r['passages'][0].source in expected_files(r['question']) for r in answerable)}/{n_ans} |",
        f"| Answerable questions with a passage above the threshold | {sum(best_score(r) >= threshold for r in answerable)}/{n_ans} |",
        f"| Off-topic questions refused before any model call | {sum(best_score(r) < threshold for r in off_topic)}/{n_off} |",
    ]
    if drafted:
        lines += [
            f"| Answerable questions answered, not refused | {sum(not r['refused'] for r in answerable)}/{n_ans} |",
            f"| Answers containing the key fact | {sum(contains_key_fact(r['draft'], r['question']) for r in answerable)}/{n_ans} |",
            f"| Off-topic questions refused, by the threshold or by the model | {sum(r['refused'] for r in off_topic)}/{n_off} |",
            f"| Off-topic questions refused by the model alone, threshold switched off | {sum(r['model_alone_refused'] for r in off_topic)}/{n_off} |",
        ]
    lines += [
        f"| Retrieval time per question, embedding call included | {seconds_summary([r['retrieve_seconds'] for r in runs])} |",
    ]
    if drafted:
        lines += [
            f"| Drafting time when the model is called | {seconds_summary([r['draft_seconds'] for r in runs if r['called_model']])} |",
            f"| Waits for the provider's rate limit, not counted in the times | {sum(r['rate_limit_waits'] for r in runs)} |",
        ]
    lines += [
        "",
        "## Candidate thresholds",
        "",
        "Best similarity score of each question compared with the threshold, before any model call.",
        "",
        f"| Threshold | Answerable questions kept (of {n_ans}) | Kept with the right file (of {n_ans}) | Off-topic questions refused (of {n_off}) |",
        "|---|---|---|---|",
    ]
    lines += [f"| {t:.2f} | {kept} | {kept_right} | {refused} |" for t, kept, kept_right, refused in threshold_rows(runs, threshold)]
    lines += [
        "",
        "## Best score per question",
        "",
        "| Id | Language | Answerable | Best score | Best file | Right file in top 5 |" + (" Refused | Key fact |" if drafted else ""),
        "|---|---|---|---|---|---|" + ("---|---|" if drafted else ""),
    ]
    for r in sorted(runs, key=best_score, reverse=True):
        q = r["question"]
        answerable_q = q["answerable"] == "yes"
        row = (
            f"| {q['id']} | {q['lang']} | {q['answerable']} | {best_score(r):.3f} | "
            f"{r['passages'][0].source if r['passages'] else ''} | "
            f"{('yes' if right_file_in(r['passages'], q) else 'no') if answerable_q else ''} |"
        )
        if drafted:
            fact = ("yes" if contains_key_fact(r["draft"], q) else "no") if answerable_q else ""
            row += f" {'yes' if r['refused'] else 'no'} | {fact} |"
        lines.append(row)
    summary = "\n".join(lines) + "\n"
    (RESULTS_DIR / "summary.md").write_text(summary, encoding="utf-8", newline="\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--threshold", type=float, default=nodes.MIN_RELEVANCE)
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between drafting calls")
    args = parser.parse_args()

    nodes.LLM_FALLBACK_MODELS = []  # measure the main model only
    questions = load_questions(EVAL_DIR / "questions.csv")
    with tempfile.TemporaryDirectory() as tmp:
        db.DUCKDB_PATH = str(Path(tmp) / "evaluation_kb.duckdb")
        chunk_count = ingest.ingest(str(DOCS_DIR), db.DUCKDB_PATH)
        runs = retrieve_all(questions)
    if not args.retrieval_only:
        draft_all(runs, args.threshold, args.pause)
    print(write_results(runs, args.threshold, chunk_count, drafted=not args.retrieval_only))


if __name__ == "__main__":
    main()
