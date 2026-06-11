.PHONY: test test-legacy test-tools lint reproduce reproduce-sample fetch claim1 claim2 claim4 index benchmark daemon clean

PYTHON ?= python3

test:
	$(PYTHON) -m unittest -v

test-legacy:
	cd legacy && $(PYTHON) -m unittest

test-tools:
	cd tools/crossover-daemon && $(PYTHON) -m unittest

lint:
	$(PYTHON) -m compileall -q .

reproduce:
	$(PYTHON) reproduce.py

reproduce-sample:
	$(PYTHON) reproduce.py --sample

fetch:
	$(PYTHON) fetch_data.py

claim1:
	$(PYTHON) claim1_peg.py

claim2:
	$(PYTHON) claim2_stability.py

claim4:
	$(PYTHON) claim4_settlement.py --demo

index:
	$(PYTHON) qi_index.py

benchmark:
	$(PYTHON) benchmark.py --minutes 5 --store

daemon:
	cd tools/crossover-daemon && $(PYTHON) daemon.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f crossover.db* settlement.db* worker.db demo_worker.db
	rm -rf results
