#!/usr/bin/env python3
"""Generate figures and results table from outputs/experiments/summary.csv."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "outputs" / "experiments"
FIGURES_DIR = PROJECT_ROOT / "paper" / "figures"
PAPER_DIR = PROJECT_ROOT / "paper"


def main() -> None:
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary_path = EXPERIMENTS_DIR / "summary.csv"
    if not summary_path.exists():
        print(f"Missing {summary_path}. Run scripts/run_experiments.py first.", file=sys.stderr)
        sys.exit(1)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(summary_path)
    df = df.fillna(0)

    # Aggregate by strategy (over all graph_size, scenario, seed) for strategy-level figures
    by_strategy = df.groupby("strategy").agg(
        cascade_size_peak_mean=("cascade_size_peak", "mean"),
        cascade_size_peak_std=("cascade_size_peak", "std"),
        sla_violations_mean=("sla_violations", "mean"),
        sla_violations_std=("sla_violations", "std"),
        throughput_completed_mean=("throughput_completed", "mean"),
        throughput_completed_std=("throughput_completed", "std"),
        mttr_mean=("mttr", "mean"),
        mttr_std=("mttr", "std"),
        total_failed_steps_mean=("total_failed_steps", "mean"),
        total_failed_steps_std=("total_failed_steps", "std"),
    ).reset_index()
    by_strategy = by_strategy.fillna(0)

    # Display names for strategies
    def label(s: str) -> str:
        if s == "OURS":
            return "Ours"
        if s == "NO_CONTAINMENT":
            return "No containment"
        if s == "STATIC_CIRCUIT_BREAKER":
            return "Circuit breaker"
        if s == "LOCAL_ONLY_ISOLATION":
            return "Local only"
        if s == "RATE_LIMIT_ONLY":
            return "Rate limit"
        return s

    strategies = by_strategy["strategy"].tolist()
    x = range(len(strategies))
    labels = [label(s) for s in strategies]

    # 1. Cascade size vs strategy
    fig, ax = plt.subplots()
    ax.bar(
        x,
        by_strategy["cascade_size_peak_mean"],
        yerr=by_strategy["cascade_size_peak_std"],
        capsize=3,
        tick_label=labels,
    )
    ax.set_ylabel("Cascade peak size (mean ± std)")
    ax.set_xlabel("Strategy")
    ax.set_title("Cascade Peak Size by Strategy")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "cascade_comparison.png", dpi=150)
    fig.savefig(FIGURES_DIR / "cascade_comparison.pdf")
    plt.close()
    print(f"Saved {FIGURES_DIR / 'cascade_comparison.png'}")

    # 2. SLA violations vs strategy
    fig, ax = plt.subplots()
    ax.bar(
        x,
        by_strategy["sla_violations_mean"],
        yerr=by_strategy["sla_violations_std"],
        capsize=3,
        tick_label=labels,
    )
    ax.set_ylabel("SLA violations (mean ± std)")
    ax.set_xlabel("Strategy")
    ax.set_title("SLA Violations by Strategy")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "sla_vs_strategy.png", dpi=150)
    fig.savefig(FIGURES_DIR / "sla_vs_strategy.pdf")
    plt.close()
    print(f"Saved {FIGURES_DIR / 'sla_vs_strategy.png'}")

    # 3. Throughput comparison
    fig, ax = plt.subplots()
    ax.bar(
        x,
        by_strategy["throughput_completed_mean"],
        yerr=by_strategy["throughput_completed_std"],
        capsize=3,
        tick_label=labels,
    )
    ax.set_ylabel("Throughput (mean ± std)")
    ax.set_xlabel("Strategy")
    ax.set_title("Throughput by Strategy")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "throughput_comparison.png", dpi=150)
    fig.savefig(FIGURES_DIR / "throughput_comparison.pdf")
    plt.close()
    print(f"Saved {FIGURES_DIR / 'throughput_comparison.png'}")

    # 4. MTTR comparison
    fig, ax = plt.subplots()
    ax.bar(
        x,
        by_strategy["mttr_mean"],
        yerr=by_strategy["mttr_std"],
        capsize=3,
        tick_label=labels,
    )
    ax.set_ylabel("MTTR (mean ± std)")
    ax.set_xlabel("Strategy")
    ax.set_title("MTTR by Strategy")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "mttr_comparison.png", dpi=150)
    fig.savefig(FIGURES_DIR / "mttr_comparison.pdf")
    plt.close()
    print(f"Saved {FIGURES_DIR / 'mttr_comparison.png'}")

    # 5. Containment aggressiveness (total_failed_steps) vs SLA violations
    fig, ax = plt.subplots()
    for s in df["strategy"].unique():
        sub = df[df["strategy"] == s]
        ax.scatter(
            sub["total_failed_steps"],
            sub["sla_violations"],
            label=label(s),
            alpha=0.5,
            s=15,
        )
    ax.set_xlabel("Total failed steps (containment aggressiveness proxy)")
    ax.set_ylabel("SLA violations")
    ax.set_title("Containment vs SLA Violations")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "containment_vs_sla.png", dpi=150)
    fig.savefig(FIGURES_DIR / "containment_vs_sla.pdf")
    plt.close()
    print(f"Saved {FIGURES_DIR / 'containment_vs_sla.png'}")

    # 5. Generate results_table.tex (aggregated by strategy and graph_size)
    agg = df.groupby(["strategy", "graph_size"]).agg(
        cascade_mean=("cascade_size_peak", "mean"),
        cascade_std=("cascade_size_peak", "std"),
        failed_mean=("total_failed_steps", "mean"),
        failed_std=("total_failed_steps", "std"),
        sla_mean=("sla_violations", "mean"),
        sla_std=("sla_violations", "std"),
        throughput_mean=("throughput_completed", "mean"),
        throughput_std=("throughput_completed", "std"),
        mttr_mean=("mttr", "mean"),
        mttr_std=("mttr", "std"),
    ).reset_index()
    agg = agg.fillna(0)

    # Build LaTeX table: one table per graph_size, or one combined table with strategy and size
    lines = [
        "% Auto-generated from scripts/generate_figures.py. Do not edit by hand.",
        "\\begin{table}[t]",
        "\\caption{Mean $\\pm$ std over seeds and scenarios.}",
        "\\label{tab:results}",
        "\\centering",
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        "Strategy & Size & Cascade peak & Failed steps & SLA viol. & Throughput & MTTR \\\\",
        "\\midrule",
    ]
    for _, row in agg.iterrows():
        strat = row["strategy"]
        if strat == "OURS":
            strat = "Ours"
        elif strat == "NO_CONTAINMENT":
            strat = "No containment"
        elif strat == "STATIC_CIRCUIT_BREAKER":
            strat = "Circuit breaker"
        elif strat == "LOCAL_ONLY_ISOLATION":
            strat = "Local only"
        elif strat == "RATE_LIMIT_ONLY":
            strat = "Rate limit"
        c_m, c_s = row["cascade_mean"], row["cascade_std"]
        f_m, f_s = row["failed_mean"], row["failed_std"]
        sla_m, sla_s = row["sla_mean"], row["sla_std"]
        t_m, t_s = row["throughput_mean"], row["throughput_std"]
        m_m, m_s = row["mttr_mean"], row["mttr_std"]
        lines.append(
            f"{strat} & {int(row['graph_size'])} & "
            f"{c_m:.1f} $\\pm$ {c_s:.1f} & {f_m:.0f} $\\pm$ {f_s:.0f} & "
            f"{sla_m:.1f} $\\pm$ {sla_s:.1f} & {t_m:.1f} $\\pm$ {t_s:.1f} & "
            f"{m_m:.1f} $\\pm$ {m_s:.1f} \\\\"
        )
    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    table_path = PAPER_DIR / "results_table.tex"
    table_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved {table_path}")
    print("Done.")


if __name__ == "__main__":
    main()
