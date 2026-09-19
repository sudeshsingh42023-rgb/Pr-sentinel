.PHONY: install test review index-conventions benchmark

install:
	pip install -r requirements.txt

test:
	PYTHONPATH=src pytest tests/ -v

review:
	PYTHONPATH=src python -m pr_sentinel.cli review --base $(BASE) --head $(HEAD) --intent "$(INTENT)"

review-file:
	PYTHONPATH=src python -m pr_sentinel.cli review --diff-file $(FILE) --intent "$(INTENT)"

index-conventions:
	PYTHONPATH=src python -m pr_sentinel.cli index-conventions --repo $(REPO)

benchmark:
	PYTHONPATH=src python -m pr_sentinel.bench.run_benchmark --benchmark data/benchmark.jsonl --out results/benchmark.json

benchmark-smoke:
	PYTHONPATH=src python -m pr_sentinel.bench.run_benchmark --benchmark data/benchmark.example.jsonl --out results/smoke.json
