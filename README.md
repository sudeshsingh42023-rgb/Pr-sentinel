# Intent-spec A/B protocol

Tests the claim: a structured intent spec produces a higher first-pass task
success rate than a freeform prompt of similar length, for the same coding
agent on the same task.

## 1. Write 30-50 small, checkable tasks

Each task needs a machine-checkable acceptance test (a pytest function, not
"looks reasonable"). Example: "add input validation to `parse_amount()` that
rejects negative numbers" with a test asserting `parse_amount(-5)` raises.

`tasks.jsonl` schema:
```json
{"id": "t001", "task": "...", "repo_context": "...", "acceptance_tests": ["def test_...(): ..."]}
```

## 2. Run each task under two conditions

- **freeform**: hand the task description straight to your coding agent.
- **structured**: run `expand_task_to_spec()` (in `pr_sentinel/intent.py`) to
  produce a bounded YAML spec, then hand *that* to the same agent instead.

## 3. Score both

- Run the acceptance tests via `pr_sentinel.sandbox.run_proposed_test`.
- Count files touched outside `in_scope_files` as scope violations
  (`score_diff_against_spec`).
- Call `summarize()` on the collected `TaskResult`s.

## 4. Report

Mean success rate and mean scope violations, per condition, with the n. This
is the experiment that answers the JD's "specify intent prompts for AI coding
agents" line with a number instead of an opinion.
