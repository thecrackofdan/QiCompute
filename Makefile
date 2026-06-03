.PHONY: test test-unit test-integration test-simulation demo stress lint clean
.PHONY: smoke
.PHONY: load-small load-medium bottleneck perf

PYTHON ?= python3

test:
	$(PYTHON) -m unittest -v

test-unit:
	$(PYTHON) run_tests.py --unit

test-integration:
	$(PYTHON) run_tests.py --integration

test-simulation:
	$(PYTHON) run_tests.py --simulation

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

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f worker.db demo_worker.db
