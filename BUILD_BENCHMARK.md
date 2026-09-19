# Building the benchmark

The benchmark is what turns "I built a PR review bot" into a measured claim.
Don't skip it, and don't hand-write `known_issues` to match whatever the agent
finds — that's circular and an interviewer who's built evals will spot it in
one follow-up question.

## Where to get ground truth

Pick a public repo (your own past project, or a mid-size open-source repo with
clean git history). For 40-60 merged PRs:

1. **"Buggy" PRs**: find a merged PR, then check whether a later commit fixed
   something in the same files within a reasonable window (say, 30 days) with
   a message like "fix", "bug", "regression". If so, that original PR had a
   real issue your reviewer should catch. The fixing commit tells you the
   file and approximate line (`git log -p --follow <file>` around that commit).
2. **"Clean" PRs**: merged PRs with no such follow-up fix. These test your
   **false-positive rate** — equally important as recall, and the metric most
   fresher projects skip entirely.

Aim for roughly 60% buggy / 40% clean so both precision and recall are
measurable.

## Extracting the diff

```bash
git diff <PR_base_sha>...<PR_head_sha> > data/prs/pr001.diff
```

## Schema

`data/benchmark.jsonl`, one line per PR:

```json
{
  "id": "pr001",
  "diff_path": "data/prs/pr001.diff",
  "intent": "<the PR title + description, verbatim>",
  "known_issues": [
    {"file": "src/payment.py", "line": 142, "category": "correctness"}
  ],
  "clean": false
}
```

For a clean PR: `"known_issues": []`, `"clean": true`.

## Validate before spending API budget

```bash
python -c "from pr_sentinel.bench.run_benchmark import load_benchmark; load_benchmark('data/benchmark.jsonl')"
```

## Run it

```bash
make benchmark
```

## What "good" looks like

There's no universal target — report what you measured honestly. As a sanity
check: if precision and recall are both above ~0.9, be suspicious of your
benchmark's difficulty (are the "bugs" too obvious?) before believing the
agents are that good. If false-positive rate on clean PRs is above ~0.3, the
crew is too trigger-happy to actually deploy — say so in the README rather
than hiding it.
