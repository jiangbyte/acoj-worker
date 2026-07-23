#!/usr/bin/env python3
"""读取 benchmark JSON 结果，生成组合图表 (PNG) + Markdown 表格。

用法：
  python scripts/generate_benchmark_chart.py [--input docs/benchmark_result.json] [--output docs/benchmark.png]

依赖：
  pip install matplotlib
"""

import argparse
import json
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def format_table(results: dict) -> str:
    """生成 Markdown 表格（每语言一行）。"""
    lines = [
        "| 语言 | 测试 | 请求 | 成功 | 耗时(s) | 吞吐(req/s) | P50/P95/P99(ms) | 平均延迟(ms) |",
        "|------|------|------|------|---------|-------------|-----------------|-------------|",
    ]
    for lang in ("C++", "Python"):
        if lang not in results:
            continue
        data = results[lang]
        if "error" in data:
            lines.append(f"| {lang} | - | - | 失败: {data['error']} | - | - | - | - |")
            continue
        b = data.get("burst_ac", {})
        lines.append(
            f"| {lang} | Burst AC | {BURST_COUNT} | {b.get('success', '?')}/{b.get('failed', '?')} | "
            f"{b.get('duration_sec', '?')} | {b.get('throughput_req_per_sec', '?')} | "
            f"{b.get('latency_p50_ms', '?')}/{b.get('latency_p95_ms', '?')}/{b.get('latency_p99_ms', '?')} | "
            f"{b.get('latency_mean_ms', '?')} |"
        )
        s = data.get("sustained", {})
        lines.append(
            f"| {lang} | Sustained | {s.get('total', '?')} | {s.get('success', '?')}/{s.get('failed', '?')} | "
            f"{s.get('duration_sec', '?')} | {s.get('throughput_req_per_sec', '?')} | - | - |"
        )
        m = data.get("mixed", {})
        v = m.get("verdicts", {})
        vstr = " ".join(f"{k}={v}" for k, v in sorted(v.items()))
        lines.append(
            f"| {lang} | Mixed | {m.get('total', '?')} | {vstr} | "
            f"{m.get('duration_sec', '?')} | - | - | - |"
        )

    # 判题模式对比
    jm = results.get("JudgeMode", {})
    if jm:
        lines.append("|判题模式对比|---|---|---|---|---|---|---|")
        for mode in ("STANDARD(C++)", "SPJ(C++)", "SPJ(Python)", "INTERACTIVE(C++)", "INTERACTIVE(Python)"):
            d = jm.get(mode, {})
            lines.append(
                f"| C++ | {mode} | {d.get('total', '?')} | {d.get('success', '?')}/{d.get('failed', '?')} | "
                f"{d.get('duration_sec', '?')} | {d.get('throughput_req_per_sec', '?')} | "
                f"{d.get('latency_p50_ms', '?')}/{d.get('latency_p95_ms', '?')}/{d.get('latency_p99_ms', '?')} | "
                f"{d.get('latency_mean_ms', '?')} |"
            )
    return "\n".join(lines)


def generate_chart(results: dict, output_path: str) -> None:
    """生成组合图表。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("需要安装 matplotlib: pip install matplotlib")
        raise

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), gridspec_kw={"hspace": 0.35, "wspace": 0.3})
    fig.suptitle("acoj-worker Performance Benchmark (Python)", fontsize=14, fontweight="bold", y=0.98)

    py = results.get("Python", {})
    b = py.get("burst_ac", {})
    s = py.get("sustained", {})

    # ── 左上: 延迟分布直方图 ──
    ax = axes[0, 0]
    latencies = b.get("latencies_flat", [])
    if latencies:
        ax.hist(latencies, bins=30, color="#4C72B0", alpha=0.7, edgecolor="white")
        for p, color, label in [
            (b.get("latency_p50_ms", 0), "#DD8452", "P50"),
            (b.get("latency_p95_ms", 0), "#55A868", "P95"),
            (b.get("latency_p99_ms", 0), "#C44E52", "P99"),
        ]:
            ax.axvline(p, color=color, ls="--", lw=1.5, label=f"{label}={p}ms")
        ax.legend(fontsize=8)
    ax.set_xlabel("Latency (ms)", fontsize=9)
    ax.set_ylabel("Frequency", fontsize=9)
    ax.set_title("Burst AC Latency Distribution", fontsize=11)
    ax.tick_params(axis="both", labelsize=8)

    # ── 右上: 吞吐柱状图 ──
    ax = axes[0, 1]
    labels = ["Burst AC", "Sustained"]
    vals = [b.get("throughput_req_per_sec", 0), s.get("throughput_req_per_sec", 0)]
    bars = ax.bar(labels, vals, color=["#4C72B0", "#55A868"], width=0.5, edgecolor="white")
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f"{val}", ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Throughput (req/s)", fontsize=9)
    ax.set_title("Throughput Comparison", fontsize=11)
    ax.tick_params(axis="both", labelsize=8)

    # ── 左下: 成功率 ──
    ax = axes[1, 0]
    burst_success = b.get("success", 0) / max(BURST_COUNT, 1) * 100
    sustained_success = s.get("success", 0) / max(s.get("total", 1), 1) * 100
    rate_labels = ["Burst AC", "Sustained"]
    rate_vals = [burst_success, sustained_success]
    bars = ax.bar(rate_labels, rate_vals, color=["#4C72B0", "#55A868"], width=0.5, edgecolor="white")
    for bar, val in zip(bars, rate_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f"{val:.0f}%", ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Success Rate (%)", fontsize=9)
    ax.set_title("Success Rate", fontsize=11)
    ax.set_ylim(0, 105)
    ax.tick_params(axis="both", labelsize=8)

    # ── 右下: 混合负载 ──
    ax = axes[1, 1]
    m = py.get("mixed", {})
    verdicts = m.get("verdicts", {})
    if verdicts:
        v_labels = list(verdicts.keys())
        v_values = list(verdicts.values())
        colors = []
        for v in v_labels:
            if v == "AC": colors.append("#4C72B0")
            elif v == "WA": colors.append("#DD8452")
            elif v == "TLE": colors.append("#C44E52")
            else: colors.append("#8172B3")
        bars = ax.bar(v_labels, v_values, color=colors, width=0.5, edgecolor="white")
        for bar, val in zip(bars, v_values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                    str(val), ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Count", fontsize=9)
    ax.set_title("Mixed Load Verdict Distribution", fontsize=11)
    ax.tick_params(axis="both", labelsize=8)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


BURST_COUNT = 64


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark chart from JSON results")
    parser.add_argument("--input",
                        default=os.path.join(_project_root, "docs", "benchmark_result.json"))
    parser.add_argument("--output",
                        default=os.path.join(_project_root, "docs", "benchmark.png"))
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"未找到 benchmark 结果文件: {args.input}")
        print("请先运行: python tests/run_benchmark.py")
        sys.exit(1)

    with open(args.input) as f:
        results = json.load(f)

    generate_chart(results, args.output)
    print(f"图表已生成: {args.output}")

    print("\n## 性能基准\n")
    print(format_table(results))


if __name__ == "__main__":
    main()
