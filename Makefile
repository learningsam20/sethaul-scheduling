.PHONY: start stop build reset scenarios concurrency crunch package deploy test

start:
	./scripts/start.sh

stop:
	./scripts/stop.sh

build:
	./scripts/build.sh

reset:
	./scripts/reset_db.sh

scenarios:
	./scripts/run_scenarios.sh

concurrency:
	./scripts/concurrency_demo.sh

crunch:
	python3 scripts/evening_crunch.py

test:
	backend/.venv/bin/pytest -q

package:
	./scripts/package.sh

deploy:
	./scripts/deploy.sh
