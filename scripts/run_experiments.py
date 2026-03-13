#!/usr/bin/env python3
"""Run experiments; write summary.csv and aggregated CSVs to outputs/experiments/."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Run from project root so risk_containment is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


def build_graph(cfg: dict, size: int, seed: int, use_simulator: bool = False):
    gtype = cfg.get("graph", {}).get("type", "scale_free")
    json_path = cfg.get("graph", {}).get("json_path")
    if gtype == "json" and json_path:
        path = Path(json_path) if str(json_path).startswith("/") else PROJECT_ROOT / json_path
        return load_graph_from_json(str(path))
    if use_simulator:
        try:
            from simulator.graph_generator import (
                create_scale_free_graph,
                create_small_world_graph,
                create_random_graph,
            )
            if gtype == "small_world":
                return create_small_world_graph(n=size, seed=seed)
            if gtype == "random":
                return create_random_graph(n=size, p=0.08, seed=seed)
            return create_scale_free_graph(n=size, m=2, seed=seed)
        except ImportError:
            pass
    if gtype == "small_world":
        return small_world_directed(n=size, seed=seed)
    return scale_free_directed(n=size, seed=seed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run validation experiments")
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "configs" / "full_validation.yaml"),
        help="Config YAML path",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory (default: outputs/experiments)",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=None,
        help="Override number of seeds (default: from config)",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=None,
        help="Override graph sizes (default: from config)",
    )
    parser.add_argument(
        "--use-simulator",
        action="store_true",
        help="Use simulator package (Poisson workload, realistic failure model, NetworkX graph models).",
    )
    args = parser.parse_args()
    cfg = load_config(args.config)
    out_dir = args.output_dir or cfg.get("output", {}).get("dir", "outputs/experiments")
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    timeseries_dir = out_dir / "timeseries"
    timeseries_dir.mkdir(parents=True, exist_ok=True)

    sizes = args.sizes or cfg.get("graph", {}).get("sizes", [50, 200, 500])
    steps = cfg.get("simulation", {}).get("steps", 200)
    requests = cfg.get("simulation", {}).get("requests_per_entry", 30)
    seeds = args.seeds if args.seeds is not None else cfg.get("simulation", {}).get("seeds", 20)
    strategies = cfg.get("strategies", [
        "NO_CONTAINMENT",
        "STATIC_CIRCUIT_BREAKER",
        "LOCAL_ONLY_ISOLATION",
        "RATE_LIMIT_ONLY",
        "OURS",
    ])
    scenarios = cfg.get("scenarios", ["S1", "S2", "S3", "S4"])

    total = len(sizes) * len(strategies) * len(scenarios) * seeds
    try:
        from tqdm import tqdm
        pbar = tqdm(total=total, desc="Experiments", unit="run")
    except ImportError:
        pbar = None

    summary_rows = []
    use_simulator = getattr(args, "use_simulator", False)

    if use_simulator:
        from simulator.runner import run_and_metrics
        from simulator.scenarios import get_scenario_injector as sim_get_scenario

    for size in sizes:
        for strategy_name in strategies:
            if use_simulator:
                for scenario_name in scenarios:
                    for seed in range(seeds):
                        G = build_graph(cfg, size, seed, use_simulator=True)
                        scenario_inject = sim_get_scenario(scenario_name, G, steps, seed)
                        metrics = run_and_metrics(
                            G, steps, seed, strategy_name, scenario_name,
                            scenario_inject=scenario_inject,
                            lambda_per_entry=requests,
                        )
                        summary_rows.append(metrics)
                        if pbar:
                            pbar.update(1)
                continue
            isolate_fn, recover_fn, pre_step_fn = get_strategy(strategy_name)
            for scenario_name in scenarios:
                for seed in range(seeds):
                    G = build_graph(cfg, size, seed, use_simulator=False)
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
                        {
                            "strategy": strategy_name,
                            "scenario": scenario_name,
                            "seed": seed,
                            "graph_size": size,
                        },
                    )
                    ts_path = timeseries_dir / f"ts_size{size}_{strategy_name}_{scenario_name}_seed{seed}.csv"
                    pd.DataFrame(ts_rows).to_csv(ts_path, index=False)
                    if pbar:
                        pbar.update(1)

    if pbar:
        pbar.close()

    df = pd.DataFrame(summary_rows)
    summary_path = out_dir / "summary.csv"
    df.to_csv(summary_path, index=False)
    print(f"Wrote {summary_path} ({len(df)} rows)")
    per_run_path = out_dir / "per_run_metrics.csv"
    df.to_csv(per_run_path, index=False)
    print(f"Wrote {per_run_path}")

    # Aggregate by (strategy, graph_size): mean and std over scenario and seed
    agg = df.groupby(["strategy", "graph_size"]).agg(
        cascade_size_peak_mean=("cascade_size_peak", "mean"),
        cascade_size_peak_std=("cascade_size_peak", "std"),
        total_failed_steps_mean=("total_failed_steps", "mean"),
        total_failed_steps_std=("total_failed_steps", "std"),
        time_to_containment_mean=("time_to_containment", "mean"),
        time_to_containment_std=("time_to_containment", "std"),
        sla_violations_mean=("sla_violations", "mean"),
        sla_violations_std=("sla_violations", "std"),
        throughput_completed_mean=("throughput_completed", "mean"),
        throughput_completed_std=("throughput_completed", "std"),
        mttr_mean=("mttr", "mean"),
        mttr_std=("mttr", "std"),
        false_isolations_mean=("false_isolations", "mean"),
        false_isolations_std=("false_isolations", "std"),
    ).reset_index()
    agg = agg.fillna(0)

    cascade_metrics = agg[
        [
            "strategy", "graph_size",
            "cascade_size_peak_mean", "cascade_size_peak_std",
            "total_failed_steps_mean", "total_failed_steps_std",
            "time_to_containment_mean", "time_to_containment_std",
        ]
    ]
    cascade_path = out_dir / "cascade_metrics.csv"
    cascade_metrics.to_csv(cascade_path, index=False)
    print(f"Wrote {cascade_path}")

    throughput_metrics = agg[
        [
            "strategy", "graph_size",
            "throughput_completed_mean", "throughput_completed_std",
            "sla_violations_mean", "sla_violations_std",
            "mttr_mean", "mttr_std",
            "false_isolations_mean", "false_isolations_std",
        ]
    ]
    throughput_path = out_dir / "throughput_metrics.csv"
    throughput_metrics.to_csv(throughput_path, index=False)
    print(f"Wrote {throughput_path}")

    print("Done. Next: python scripts/generate_figures.py")


if __name__ == "__main__":
    main()
