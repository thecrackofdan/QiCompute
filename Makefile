.PHONY: test demo stress lint clean
.PHONY: smoke

PYTHON ?= python3

test:
	$(PYTHON) -m unittest -v

demo:
	$(PYTHON) demo.py --mode honest

stress:
	$(PYTHON) market.py --stress-sim

smoke:
	$(PYTHON) lan_smoke_test.py

lint:
	$(PYTHON) -m compileall -q .

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f worker.db demo_worker.db
