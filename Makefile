NET ?= regtest

.PHONY: help demo-close demo-liq

help:
	@echo "SSV demos (regtest)"
	@echo "  make demo-close   # run CLOSE+REPAY skeleton (prompts to attach RGB anchor)"
	@echo "  make demo-liq     # run CSV LIQUIDATE skeleton"

demo-close:
	bash examples/close_repay_demo.sh

demo-liq:
	bash examples/liq_demo.sh

