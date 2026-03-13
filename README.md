# Dynamic Risk Propagation and Failure Containment

Simulator and experiment pipeline for microservice cascade containment (graph-based risk propagation, hysteresis, chaos scenarios). All metrics come from simulator runs; no synthetic results.

**Repo:** [github.com/code-ninja-bayyavarapu/Dynamic-Risk-Propagation-and-Failure-Containment-in-Large-Scale-Enterprise-Microservice-Graphs](https://github.com/code-ninja-bayyavarapu/Dynamic-Risk-Propagation-and-Failure-Containment-in-Large-Scale-Enterprise-Microservice-Graphs)

---

## Run in Google Colab

1. Open [Colab](https://colab.research.google.com/), **File → Open notebook** (or upload).
2. **Clone and go to project root:**
   ```python
   !git clone https://github.com/code-ninja-bayyavarapu/Dynamic-Risk-Propagation-and-Failure-Containment-in-Large-Scale-Enterprise-Microservice-Graphs.git
   %cd Dynamic-Risk-Propagation-and-Failure-Containment-in-Large-Scale-Enterprise-Microservice-Graphs
   ```
3. Open **`notebooks/microservice_cascade_experiments.ipynb`** in Colab (upload it or open from the cloned folder).
4. **Run all cells.** The notebook will:
   - Install dependencies (`numpy`, `pandas`, `networkx`, `matplotlib`, `pyyaml`, `tqdm`)
   - Run experiments (default quick run: 50 nodes, 2 seeds)
   - Generate figures and show summary table
   - List output paths for CSV and plots

Use **CPU runtime**; no GPU needed.

To run a larger experiment from the notebook, edit the experiment cell and use e.g. `--seeds 5 --sizes 50 200` or remove the `--seeds`/`--sizes` overrides to use the full config.

---

## Run locally

```bash
git clone https://github.com/code-ninja-bayyavarapu/Dynamic-Risk-Propagation-and-Failure-Containment-in-Large-Scale-Enterprise-Microservice-Graphs.git
cd Dynamic-Risk-Propagation-and-Failure-Containment-in-Large-Scale-Enterprise-Microservice-Graphs
pip install -r requirements.txt
```

**Quick run (few minutes):**
```bash
export PYTHONPATH=.   # or set PYTHONPATH=. on Windows
python scripts/run_experiments.py --use-simulator --seeds 2 --sizes 50
python scripts/generate_figures.py
```

**Full run (config: 50, 200, 500 nodes; 20 seeds; 200 steps):**
```bash
export PYTHONPATH=.
python scripts/run_experiments.py --use-simulator --config configs/full_validation.yaml
python scripts/generate_figures.py
```

Outputs: `outputs/experiments/summary.csv`, `per_run_metrics.csv`, `cascade_metrics.csv`, `throughput_metrics.csv`; figures under `paper/figures/` (or create `outputs/figures` and point the script there if you prefer).

---

## Tests

```bash
pip install pytest
PYTHONPATH=. pytest tests/ -v
```

---

## Layout

| Path | Purpose |
|------|--------|
| `risk_containment/` | Core models, graph gen, simulator step, strategies, metrics |
| `simulator/` | Graph generator (scale-free/small-world/random), workload, failure model, scenarios, runner |
| `scripts/run_experiments.py` | Batch runs; writes CSVs to `outputs/experiments/` |
| `scripts/generate_figures.py` | Reads summary CSV; writes figures and optional results table |
| `notebooks/microservice_cascade_experiments.ipynb` | Colab: install, run, plot, display |
| `configs/` | YAML configs (graph sizes, seeds, strategies, scenarios) |

Experiments are deterministic for a given seed and config.

---

## Updating the repo

After local changes (no paper, outputs, or `idea.txt`):

```bash
git add -A
git status   # confirm only intended files
git commit -m "Your message"
git push origin master
```
