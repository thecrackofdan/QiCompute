.PHONY: test demo stress lint clean

PYTHON ?= python3

test:
	$(PYTHON) -m unittest -v

demo:
	$(PYTHON) demo.py --mode honest

stress:
	$(PYTHON) market.py --stress-sim

lint:
	$(PYTHON) -m compileall -q .

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f worker.db demo_worker.db
