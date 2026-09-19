# How to finish this before it goes on your resume

Generated offline, so it hasn't been run against a live model API here. Do
these in order.

## 1. Install and unit-test (15 min)

```bash
pip install -r requirements.txt
make test
```

All of these tests run with zero API calls (diff parsing, secret-prescan regex,
benchmark matching logic, config). If one fails, fix it — that's a real bug.

## 2. Run the crew on the sample diff (15 min)

```bash
export ANTHROPIC_API_KEY=...
make review-file FILE=examples/sample.diff INTENT="$(cat examples/sample_intent.txt)"
```

The sample diff has two planted issues: a hardcoded API key and an unguarded
`old_value == 0` division. Confirm the security and correctness agents both
catch them. If the arbiter's `should_block_merge` isn't `true`, look at
`config.yaml`'s `block_severity` before assuming the agents are wrong.

## 3. Index a real repo's conventions (15 min)

```bash
make index-conventions REPO=/path/to/some/repo/you/have/locally
```

Pick a repo with real, consistent patterns (a mature open-source repo works
well). Re-run the review and check the convention agent actually retrieves
relevant examples — if it returns `no_matching_examples` on everything, your
BM25 query text (currently the raw diff) may need tuning for that codebase.

## 4. Build the benchmark (2-4 hours — this is the actual project)

See `BUILD_BENCHMARK.md`. In short: pick a public repo, pull 40-60 merged PRs,
label each with its known outcome (a follow-up bugfix commit within N days =
a caught-late bug; no follow-up = clean). This is what turns "I built a review
bot" into "I measured precision and recall on real PRs."

```bash
make benchmark-smoke   # sanity check the harness first
make benchmark          # the real run
```

## 5. Run the intent-spec A/B (1-2 hours)

Per `intent/README.md`: write 30-50 small tasks with checkable acceptance
tests, run each under freeform vs structured-spec conditions against whichever
coding agent you have access to, score with `pr_sentinel.sandbox` +
`intent.summarize()`.

## 6. Fill in the README tables

Copy real numbers from `results/benchmark.json` and `results/intent_ab.json`.
Write the one-paragraph "what I found" — which agent drove false positives,
whether the structured spec actually helped and by how much, what you'd fix
next. That paragraph is what an interviewer remembers, not the table.

## 7. Optional but strong

- Wire the GitHub Action (`sentinel-review.yml`) onto a real repo you control
  and open a test PR with a deliberate bug — screenshot the posted review
  comment for the README.
- Swap the security regex prescan for a real scanner (gitleaks) in front of
  the LLM agent and note the precision change.
