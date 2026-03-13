"""Experiment runner: run all strategies x scenarios x sizes x seeds and produce outputs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
import yaml

from risk_containment.graph_gen import (
    load_graph_from_json,
    scale_free_directed,
    small_world_directed,
)
from risk_containment.metrics import compute_metrics, snapshots_to_timeseries_csv
from risk_containment.scenarios import get_scenario_injector
from risk_containment.simulator import run_simulation
from risk_containment.strategies import get_strategy


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_graph(cfg: dict, size: int, seed: int):
    gtype = cfg.get("graph", {}).get("type", "scale_free")
    json_path = cfg.get("graph", {}).get("json_path")
    if gtype == "json" and json_path:
        return load_graph_from_json(json_path)
    if gtype == "small_world":
        return small_world_directed(n=size, seed=seed)
    return scale_free_directed(n=size, seed=seed)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml", help="Config YAML path")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument("--quick", action="store_true", help="Quick run: sizes=[50], seeds=3")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.quick:
        cfg.setdefault("graph", {})["sizes"] = [50]
        cfg.setdefault("simulation", {})["seeds"] = 3
    out_dir = args.output_dir or cfg.get("output", {}).get("dir", "outputs")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if args.output_dir:
        timeseries_dir = os.path.join(out_dir, "timeseries")
        figures_dir = os.path.join(out_dir, "figures")
    else:
        timeseries_dir = cfg.get("output", {}).get("timeseries_dir", os.path.join(out_dir, "timeseries"))
        figures_dir = cfg.get("output", {}).get("figures_dir", os.path.join(out_dir, "figures"))
    Path(timeseries_dir).mkdir(parents=True, exist_ok=True)
    Path(figures_dir).mkdir(parents=True, exist_ok=True)

    sizes = cfg.get("graph", {}).get("sizes", [50, 200, 500, 1000])
    steps = cfg.get("simulation", {}).get("steps", 200)
    requests = cfg.get("simulation", {}).get("requests_per_entry", 30)
    seeds = cfg.get("simulation", {}).get("seeds", 20)
    strategies = cfg.get("strategies", ["NO_CONTAINMENT", "OURS"])
    scenarios = cfg.get("scenarios", ["S1", "S2", "S3", "S4"])

    summary_rows = []
    try:
        from tqdm import tqdm
        outer = tqdm(list(range(len(sizes) * len(strategies) * len(scenarios) * seeds)), desc="Experiments")
    except ImportError:
        outer = list(range(len(sizes) * len(strategies) * len(scenarios) * seeds))

    count = 0
    for size in sizes:
        for strategy_name in strategies:
            isolate_fn, recover_fn, pre_step_fn = get_strategy(strategy_name)
            for scenario_name in scenarios:
                for seed in range(seeds):
                    G = build_graph(cfg, size, seed)
                    scenario_inject = get_scenario_injector(scenario_name, G, steps, seed)
                    def pre_step(G_inner, step_index: int):
                        if scenario_inject:
                            scenario_inject(G_inner, step_index)
                        if pre_step_fn:
                            pre_step_fn(G_inner, step_index)
                    snapshots = run_simulation(
                        G,
                        seed=seed,
                        steps=steps,
                        requests_per_entry=requests,
                        strategy_isolate=isolate_fn,
                        strategy_recover=recover_fn,
                        strategy_pre_step=pre_step if (scenario_inject or pre_step_fn) else None,
                    )
                    metrics = compute_metrics(
                        snapshots, G, strategy_name, scenario_name, seed, G.number_of_nodes()
                    )
                    summary_rows.append(metrics)
                    ts_rows = snapshots_to_timeseries_csv(
                        snapshots,
                        {"strategy": strategy_name, "scenario": scenario_name, "seed": seed, "graph_size": size},
                    )
                    ts_path = os.path.join(
                        timeseries_dir,
                        f"ts_size{size}_{strategy_name}_{scenario_name}_seed{seed}.csv",
                    )
                    pd.DataFrame(ts_rows).to_csv(ts_path, index=False)
                    count += 1
                    if hasattr(outer, "update"):
                        outer.update(1)

    summary_path = cfg.get("output", {}).get("summary_csv") or os.path.join(out_dir, "summary.csv")
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

    try:
        from risk_containment.plotting import run_all_plots
        run_all_plots(summary_path, timeseries_dir, figures_dir)
    except Exception as e:
        print("Plotting failed:", e)

    print("Done. Summary:", summary_path, "Figures:", figures_dir)


if __name__ == "__main__":
    main()
