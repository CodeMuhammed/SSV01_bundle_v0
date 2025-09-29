NET ?= regtest

.PHONY: help demo-close demo-liq docker-up docker-down docker-logs test

help:
	@echo "SSV demos (docker, regtest)"
	@echo "  make docker-up    # build and start bitcoind+ssv containers"
	@echo "  make docker-logs  # tail bitcoind logs"
	@echo "  make demo-close   # run CLOSE+REPAY skeleton (dockerized; prompts to attach RGB anchor)"
	@echo "  make demo-liq     # run CSV LIQUIDATE skeleton (dockerized)"
	@echo "  make docker-down  # stop and remove containers"
	@echo "  make test         # run unit tests on host (requires pip install -e '.[dev]')"

demo-close:
	bash examples/close_repay_demo_docker.sh

demo-liq:
	bash examples/liq_demo_docker.sh

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down -v

docker-logs:
	docker compose logs -f bitcoin

test:
	pytest -q
