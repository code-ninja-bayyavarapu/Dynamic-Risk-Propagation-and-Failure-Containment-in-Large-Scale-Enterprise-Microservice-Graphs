"""Publication-quality figures from experiment outputs."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def run_all_plots(
    summary_csv: str,
    timeseries_dir: str,
    figures_dir: str,
) -> None:
    """Generate all paper figures."""
    Path(figures_dir).mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(summary_csv)
    if df.empty:
        return

    # Bar: SLA violations by strategy (mean + std across seeds)
    fig, ax = plt.subplots()
    by_strategy = df.groupby("strategy").agg(
        mean=("sla_violations", "mean"),
        std=("sla_violations", "std"),
    ).fillna(0)
    by_strategy.plot(kind="bar", y="mean", yerr="std", ax=ax, capsize=3)
    ax.set_ylabel("SLA violations")
    ax.set_xlabel("Strategy")
    ax.set_title("SLA Violations by Strategy")
    leg = ax.get_legend()
    if leg:
        leg.remove()
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(os.path.join(figures_dir, "sla_violations_by_strategy.png"), dpi=150)
    fig.savefig(os.path.join(figures_dir, "sla_violations_by_strategy.pdf"))
    plt.close()

    # Line: cascade size over time for a representative run
    ts_files = list(Path(timeseries_dir).glob("*.csv"))
    if ts_files:
        rep = pd.read_csv(ts_files[0])
        if "cascade_size" in rep.columns:
            fig, ax = plt.subplots()
            ax.plot(rep["step"], rep["cascade_size"])
            ax.set_xlabel("Step")
            ax.set_ylabel("Cascade size")
            ax.set_title("Cascade Size Over Time (representative run)")
            plt.tight_layout()
            fig.savefig(os.path.join(figures_dir, "cascade_size_over_time.png"), dpi=150)
            fig.savefig(os.path.join(figures_dir, "cascade_size_over_time.pdf"))
            plt.close()

    # Bar: throughput vs strategy
    fig, ax = plt.subplots()
    by_strategy = df.groupby("strategy")["throughput_completed"].agg(["mean", "std"]).fillna(0)
    by_strategy.plot(kind="bar", y="mean", yerr="std", ax=ax, capsize=3)
    ax.set_ylabel("Throughput (completed)")
    ax.set_xlabel("Strategy")
    ax.set_title("Throughput by Strategy")
    leg = ax.get_legend()
    if leg:
        leg.remove()
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(os.path.join(figures_dir, "throughput_by_strategy.png"), dpi=150)
    fig.savefig(os.path.join(figures_dir, "throughput_by_strategy.pdf"))
    plt.close()

    # Bar: MTTR vs strategy
    fig, ax = plt.subplots()
    by_strategy = df.groupby("strategy")["mttr"].agg(["mean", "std"]).fillna(0)
    by_strategy.plot(kind="bar", y="mean", yerr="std", ax=ax, capsize=3)
    ax.set_ylabel("MTTR (steps)")
    ax.set_xlabel("Strategy")
    ax.set_title("MTTR by Strategy")
    leg = ax.get_legend()
    if leg:
        leg.remove()
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(os.path.join(figures_dir, "mttr_by_strategy.png"), dpi=150)
    fig.savefig(os.path.join(figures_dir, "mttr_by_strategy.pdf"))
    plt.close()

    # Scatter: containment aggressiveness (e.g. total_failed_steps or n_isolated proxy) vs SLA violations
    if "total_failed_steps" in df.columns:
        fig, ax = plt.subplots()
        for s in df["strategy"].unique():
            sub = df[df["strategy"] == s]
            ax.scatter(sub["total_failed_steps"], sub["sla_violations"], label=s, alpha=0.6)
        ax.set_xlabel("Total failed steps (proxy for aggressiveness)")
        ax.set_ylabel("SLA violations")
        ax.set_title("Containment vs SLA Violations")
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, "containment_vs_sla.png"), dpi=150)
        fig.savefig(os.path.join(figures_dir, "containment_vs_sla.pdf"))
        plt.close()
