# Project root: Dynamic Risk Propagation and Failure Containment
# Run from project root: make run-experiments

PYTHON := python
SCRIPTS := scripts
CONFIG  := configs/full_validation.yaml
OUT     := outputs/experiments

.PHONY: run-experiments figures clean help

help:
	@echo "Targets:"
	@echo "  run-experiments  Run experiments and generate figures + table (scripts/run_experiments.py then scripts/generate_figures.py)"
	@echo "  experiments-only Run only scripts/run_experiments.py"
	@echo "  figures-only     Run only scripts/generate_figures.py (requires $(OUT)/summary.csv)"
	@echo "  clean            Remove generated outputs and figures"

run-experiments: experiments-only figures-only
	@echo "Done. Check $(OUT)/*.csv and paper/figures/*.png"

experiments-only:
	PYTHONPATH=. $(PYTHON) $(SCRIPTS)/run_experiments.py --config $(CONFIG)
	@echo "Experiments done. Run 'make figures-only' or 'make run-experiments' to generate figures."

figures-only:
	$(PYTHON) $(SCRIPTS)/generate_figures.py

clean:
	rm -rf $(OUT)/summary.csv $(OUT)/cascade_metrics.csv $(OUT)/throughput_metrics.csv $(OUT)/timeseries
	rm -f paper/figures/cascade_comparison.png paper/figures/cascade_comparison.pdf
	rm -f paper/figures/sla_vs_strategy.png paper/figures/sla_vs_strategy.pdf
	rm -f paper/figures/throughput_comparison.png paper/figures/throughput_comparison.pdf
	rm -f paper/figures/containment_vs_sla.png paper/figures/containment_vs_sla.pdf
	rm -f paper/results_table.tex
