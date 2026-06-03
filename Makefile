.PHONY: test test-smoke test-unit test-integration test-simulation test-slow test-profile demo stress lint clean
.PHONY: smoke
.PHONY: load-small load-medium bottleneck perf determinism reliability dev-health

PYTHON ?= python3

test:
	$(PYTHON) -m unittest -v

test-smoke:
	$(PYTHON) run_tests.py --smoke

test-unit:
	$(PYTHON) run_tests.py --unit

test-integration:
	$(PYTHON) run_tests.py --integration

test-simulation:
	$(PYTHON) run_tests.py --simulation

test-slow:
	$(PYTHON) run_tests.py --slow

test-profile:
	$(PYTHON) run_tests.py --all --profile

demo:
	$(PYTHON) demo.py --mode honest

stress:
	$(PYTHON) market.py --stress-sim

smoke:
	$(PYTHON) lan_smoke_test.py

lint:
	$(PYTHON) -m compileall -q .

load-small:
	$(PYTHON) load_test.py --workers 5 --jobs 25

load-medium:
	$(PYTHON) load_test.py --workers 25 --jobs 250

bottleneck:
	$(PYTHON) bottleneck_report.py --workers 25 --jobs 500

perf:
	$(PYTHON) benchmarks.py

determinism:
	$(PYTHON) determinism.py

reliability:
	$(PYTHON) reliability_report.py

dev-health:
	$(PYTHON) dev_health.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f worker.db demo_worker.db
