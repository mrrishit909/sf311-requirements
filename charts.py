"""Step 7: charts.

    ./venv/bin/python charts.py   -> charts/01_outcomes.png, 02_parking.png, 03_spike.png, 04_channels.png,
                                     05_rejected.png, 06_traceability.png (Graphviz)
"""
import shutil
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).parent
R = HERE / "results"
INK, DIM, GRID, BG, BLUE, ORANGE, GRAY = "#f2f2f0", "#8a8a87", "#1d1d1d", "#0b0b0b", "#3987e5", "#d95926", "#9a9a96"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": INK,
    "axes.edgecolor": "#3a3a3a", "axes.labelcolor": DIM, "xtick.color": DIM, "ytick.color": DIM,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 1,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 11, "axes.titlesize": 13,
    "axes.titlelocation": "left", "axes.titlepad": 12,
})
DOT = shutil.which("dot") or str(Path.home() / "micromamba" / "envs" / "analyst" / "bin" / "dot")
LABEL = {"resolved": "resolved", "not_found_on_arrival": "gone when staff arrived (parking, encampments)",
         "no_work_needed": "no work needed", "duplicate": "duplicate", "informational": "logged for information",
         "wrong_agency": "wrong agency or outside owner", "cannot_locate": "unable to locate (other services)",
         "gone_on_arrival": "gone on arrival (other wording)", "out_of_scope": "out of scope / not accepted",
         "handed_off": "accepted / scheduled", "administrative": "administrative closure",
         "insufficient_info": "insufficient information", "cancelled": "cancelled", "unclassified": "no note / unclassified",
         "planned_work": "planned maintenance"}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(HERE / "charts" / name, dpi=150)
    plt.close(fig)


def traceability():
    spec = yaml.safe_load((HERE / "requirements.yaml").read_text())
    lines = ['digraph T {', '  graph [bgcolor="#0b0b0b", rankdir=LR, nodesep=0.12, ranksep=1.6];',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12, fontcolor="#f2f2f0", color="#3a3a3a"];',
             '  edge [color="#5a5a58", arrowhead=none];']
    color = {"Must": "#4a2414", "Should": "#1f3b5c", "Could": "#2a2a2a"}
    files = set()
    for req in spec["requirements"]:
        title = req["title"].replace('"', "'")
        lines.append(f'  "{req["id"]}" [label="{req["id"]}  {req["priority"]}\\n{title}", fillcolor="{color[req["priority"]]}"];')
        for f in dict.fromkeys(ev["file"] for ev in req["evidence"]):
            files.add(f)
            lines.append(f'  "{req["id"]}" -> "{f}";')
    for f in sorted(files):
        lines.append(f'  "{f}" [label="results/{f}", fillcolor="#141414", fontname="Menlo", fontsize=11];')
    lines.append("}")
    dot = HERE / "charts" / "traceability.dot"
    dot.write_text("\n".join(lines) + "\n")
    subprocess.run([DOT, "-Tpng", "-Gdpi=130", str(dot), "-o", str(HERE / "charts" / "06_traceability.png")], check=True)


def main():
    (HERE / "charts").mkdir(exist_ok=True)

    o = pd.read_csv(R / "outcomes.csv").iloc[::-1]
    col = {"intake": ORANGE, "moved_on": GRAY, "resolved": BLUE}
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.barh([LABEL[x] for x in o["outcome"]], o["cases"] / 1000, color=[col.get(g, "#4a4a48") for g in o["outcome_group"]], height=0.65)
    for i, (n, p) in enumerate(zip(o["cases"], o["pct_of_closed"])):
        ax.text(n / 1000 + 4, i, f"{n:,} ({p:.1f}%)", va="center", color=INK, fontsize=8.5)
    ax.set_xlim(0, o["cases"].max() / 1000 * 1.28)
    ax.set_xlabel("closed cases (thousands), Sep 2025 - Aug 2026")
    ax.grid(axis="y", visible=False)
    intake = o.loc[o["outcome_group"] == "intake", "cases"].sum()
    ax.set_title(f"How 835,343 closed SF 311 cases ended: orange = failed at intake ({intake:,})")
    save(fig, "01_outcomes.png")

    p = pd.read_csv(R / "parking_response.csv")
    fig, ax = plt.subplots(figsize=(10, 3.8))
    labels = [t.split(": ")[1] for t in p["time_to_close"]]
    ax.bar(labels, p["gone_pct"], color=ORANGE, width=0.6)
    for i, (v, n) in enumerate(zip(p["gone_pct"], p["closed_cases"])):
        ax.text(i, v + 1.5, f"{v:.1f}%", ha="center", color=INK, fontsize=10)
        ax.text(i, 2, f"{n:,} cases", ha="center", color=BG, fontsize=8)
    ax.set_ylim(0, 75)
    ax.set_ylabel("car gone when officer arrived (%)")
    ax.set_xlabel("time from report to closure (approximates response time; the data has no arrival time)")
    ax.grid(axis="x", visible=False)
    ax.set_title("Illegal parking, sidewalk and driveway reports: the longer they wait, the more often the car is gone")
    save(fig, "02_parking.png")

    s = pd.read_csv(R / "duplicate_spike.csv")
    b = pd.read_csv(R / "duplicate_spike_by_service.csv")
    b = b[b["service"] != "All services"].sort_values("flagged_closed_as_duplicate_pct")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 1.25]})
    axes[0].plot(s["flag_rate_pct"], s["recall_pct"], color=BLUE, marker="o")
    for _, r in s.iterrows():
        axes[0].annotate(f"{r['radius_m']} m, {r['days']} d", (r["flag_rate_pct"], r["recall_pct"]), xytext=(6, -12),
                         textcoords="offset points", color=INK, fontsize=8.5)
    axes[0].set_xlabel("submissions that would see a warning (%)")
    axes[0].set_ylabel("duplicates caught (%)")
    axes[0].set_xlim(0, 65); axes[0].set_ylim(0, 80)
    axes[0].set_title("All services: catching more means warning more", fontsize=12)
    picked = {"Parking Enforcement", "Graffiti Private", "Sidewalk and Curb", "Street Defect"}
    axes[1].barh(b["service"], b["flagged_closed_as_duplicate_pct"], color=[ORANGE if x in picked else GRAY for x in b["service"]], height=0.6)
    for i, v in enumerate(b["flagged_closed_as_duplicate_pct"]):
        axes[1].text(v + 0.8, i, f"{v:.1f}%", va="center", color=INK, fontsize=9)
    axes[1].axvline(30, color=DIM, linestyle="--", linewidth=1)
    axes[1].set_xlim(0, 65)
    axes[1].set_xlabel("warnings pointing at a real duplicate (%), 50 m, 3 days")
    axes[1].grid(axis="y", visible=False)
    axes[1].set_title("By service: REQ-01 keeps the four above 30%", fontsize=12)
    save(fig, "03_spike.png")

    c = pd.read_csv(R / "intake_failure_by_channel.csv")
    fig, ax = plt.subplots(figsize=(10, 3.4))
    x = np.arange(len(c))
    ax.bar(x - 0.19, c["intake_failure_pct"], width=0.38, color=ORANGE, label="observed")
    ax.bar(x + 0.19, c["expected_from_service_mix_pct"], width=0.38, color=GRAY, label="expected from what the channel is used for")
    for i, r in c.iterrows():
        ax.text(i - 0.19, r["intake_failure_pct"] + 0.4, f"{r['intake_failure_pct']:.1f}%", ha="center", color=INK, fontsize=9)
        ax.text(i + 0.19, r["expected_from_service_mix_pct"] + 0.4, f"{r['expected_from_service_mix_pct']:.1f}%", ha="center", color=INK, fontsize=9)
    ax.set_xticks(x, [f"{ch}\n{r:.2f}x expected" for ch, r in zip(c["channel"], c["observed_vs_expected"])])
    ax.set_ylim(0, 25)
    ax.set_ylabel("closed at intake (%)")
    ax.legend(frameon=False, labelcolor=INK, fontsize=9, loc="upper left", ncol=2)
    ax.grid(axis="x", visible=False)
    ax.set_title("Web reports fail at intake more than their service mix predicts; phone (agent-guided) less")
    save(fig, "04_channels.png")

    loc = pd.read_csv(R / "location_quality.csv")
    ph = pd.read_csv(R / "photo_effect.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    axes[0].bar(["no coordinates", "with coordinates"], loc["cannot_locate_pct"], color=[GRAY, BLUE], width=0.5)
    for i, v in enumerate(loc["cannot_locate_pct"]):
        axes[0].text(i, v + 0.08, f"{v:.2f}%", ha="center", color=INK, fontsize=10)
    axes[0].set_ylim(0, 4.5); axes[0].grid(axis="x", visible=False)
    axes[0].set_ylabel("ended 'unable to locate' (%)")
    axes[0].set_title("REJ-01 map pin: no real difference", fontsize=12)
    xx = np.arange(2)
    axes[1].bar(xx - 0.19, ph["cannot_locate_pct"], width=0.38, color=BLUE, label="observed")
    axes[1].bar(xx + 0.19, ph["cannot_locate_expected_pct"], width=0.38, color=GRAY, label="expected from service mix")
    axes[1].set_xticks(xx, ["mobile, no photo", "mobile, with photo"])
    axes[1].set_ylim(0, 4.5); axes[1].grid(axis="x", visible=False)
    axes[1].legend(frameon=False, labelcolor=INK, fontsize=9)
    axes[1].set_title("REJ-02 photo: observed matches expected", fontsize=12)
    fig.suptitle("Two plausible requirements the data does not support", x=0.01, ha="left", fontsize=13, color=INK)
    save(fig, "05_rejected.png")

    traceability()
    print("charts written")


if __name__ == "__main__":
    main()
