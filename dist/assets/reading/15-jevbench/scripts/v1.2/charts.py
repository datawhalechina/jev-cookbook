"""JevBench v1.2 final charts, drawn only from results/v1.2/jevbench-v1.2-results.json.

    python3 scripts/v1.2/charts.py

main-score.png   JevBench Score (4 axes, geometric mean), ranked; honorable mentions (a service on another
                 entrant's model) and partial runs greyed below, unranked
axes.png         the four axis scores per ranked system
hard-tier.png    hard-tier accuracy per system beside the mean of the three v1.1 tiers
calibration.png  calibration sub-score (ECE + probability fidelity on the hard tier)
hard-families.png hard-tier accuracy per item family (heat table)

Same palette as v1.1: colour = kind of system; every bar is labelled, so identity never rests on colour.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = Path(__file__).resolve().parents[2]
RES = json.loads((HERE / "results/v1.2/jevbench-v1.2-results.json").read_text())
OUT = HERE / "results/v1.2/charts"
OUT.mkdir(parents=True, exist_ok=True)

CLASS = {
    "jev": ("#2a78d6", "Jev (TypeSafe, closed)"),
    "jev-rebuild": ("#eb6834", "Jev rebuild (open, or open source planned)"),
    "llm-baseline": ("#1baf7a", "Instruction model"),
    "small-tool-model": ("#4a3aa7", "Small tool-calling model"),
    "jev-service": ("#7cb4f0", "Service built on Jev"),
    "classifier": ("#c0368c", "Zero-shot classifier (not a Jev rebuild)"),
    "decision-api": ("#c89410", "Closed decision model (API only)"),
}
SURFACE, INK, INK2, GRID, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#d8d7d2", "#b9b8b1"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.parse_math": False, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
SHORT = {
    "jev-1.13.0": "Jev 1.13.0", "openjev-sglang": "openjev-sglang", "system-one-open": "system-one-open",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite", "gpt-5.6-luna": "GPT-5.6 Luna (low)",
    "deepseek-flash": "DeepSeek V4.1 Flash", "open-jev-deberta-v3-large": "open-jev-deberta-v3-large",
    "needle-3": "Needle 3", "needle-3-tools": "Needle 3, options as tools", "qwen3.8-27b": "Qwen3.8 27B",
    "open-alternative-jev": "open-alternative-jev (Qwen3.5-4B)",
    "semif-qwen3.5-4b": "SemIf (Qwen3.5-4B)", "openjev-razorback16": "OpenJev razorback16 (DiffusionGemma 26B)",
    "system-one-sg": "system-one (Qwen3-8B, Goedecke)", "nimble-9b": "Bespoke Nimble 9B",
    "djev": "djev (Maisa, diffusion-gemma)",
    "laya": "Laya (421M)", "jeff": "jeff (GLiFormer 400M)", "gliner2": "GLiNER2 (gliner2.5-base)",
    "openjev-verdict": "openJev Verdict (151M)", "classifier-dev-fast": "classifier.dev (fast tier)",
    "programasweights": "ProgramAsWeights (Qwen3-0.6B)",
}


NOT_RANKED = {"partial": " (partial run)", "honorable_mention": " (honorable mention)"}


def name(s):
    r = f"{s['rank']:>2}. " if s.get("rank") else ""
    return r + SHORT.get(s["key"], s["display"]) + NOT_RANKED.get(s.get("listing", "ranked"), "")


def frame(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def stamp(fig, title, sub, foot):
    fig.text(0.01, 0.985, title, fontsize=15, weight="bold", color=INK, va="top")
    fig.text(0.01, 0.94, sub, fontsize=10.5, color=INK2, va="top")
    fig.text(0.01, 0.005, foot, fontsize=8.5, color=INK2, ha="left", va="bottom")


def legend(fig, used, y=0.04):
    h = [Patch(facecolor=CLASS[k][0], label=CLASS[k][1]) for k in CLASS if k in used]
    h.append(Patch(facecolor=MUTED, label="listed, not ranked (honorable mention or partial run)"))
    # v1.2.2 added two kinds of system, so the legend can need a second row: keep it clear of the x axis.
    ncol = 5 if len(h) <= 5 else 4
    fig.legend(handles=h, loc="lower left", bbox_to_anchor=(0.01, y), ncol=ncol,
               frameon=False, fontsize=10, labelcolor=INK2)
    return -(-len(h) // ncol)


def bars(fname, rows, value, label_fn, title, sub, foot, xmax=100):
    legend_rows = 1 if len({s["class"] for s in rows if s["ranked"]} | {"partial"}) <= 5 else 2
    extra = 0.3 * (legend_rows - 1) + 0.25 * foot.count("\n")
    h = 0.5 * len(rows) + 2.6 + extra
    # Inches of margin under the axes: one legend row (0.5 in) plus one line per footer line, and never less than 1.0.
    bottom_in = 1.0 + 0.45 * (legend_rows - 1) + 0.3 * foot.count("\n")
    fig, ax = plt.subplots(figsize=(14, h), facecolor=SURFACE)
    # left: the longest y label is "17. classifier.dev (fast tier) (honorable mention)".
    fig.subplots_adjust(left=0.3, right=0.985, top=1 - 1.05 / h, bottom=bottom_in / h)
    frame(ax)
    ys = list(range(len(rows)))[::-1]
    for y, s in zip(ys, rows):
        v = value(s)
        if v is None:
            continue
        c = MUTED if not s["ranked"] else CLASS.get(s["class"], (MUTED,))[0]
        ax.barh(y, v, color=c, height=0.66)
        ax.text(v + xmax * 0.008, y, label_fn(s, v), va="center", fontsize=10, color=INK)
    ax.set_yticks(ys, [name(s) for s in rows])
    ax.set_xlim(0, xmax * 1.45)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    stamp(fig, title, sub, foot)
    legend(fig, {s["class"] for s in rows if s["ranked"]}, y=(bottom_in - 0.5 * legend_rows) / h)
    fig.savefig(OUT / fname, dpi=150, facecolor=SURFACE)
    plt.close(fig)


COST_EXAMPLE = ""


def main():
    sys_ = RES["systems"]
    global COST_EXAMPLE
    COST_EXAMPLE = RES["cost_unit"]["short_note"]
    ranked = [s for s in sys_ if s["ranked"]]
    honorable = [s for s in sys_ if s.get("listing") == "honorable_mention"]
    part = [s for s in sys_ if s["partial"]]
    n_hard = RES["tiers"]["hard"]
    cost = lambda s: ({"estimate": "est. ", "announced": "announced "}.get(s["cost"]["kind"], "")) + f"${s['cost']['usd_per_1000']:.3f}"
    ax4 = lambda s: s["axes"]
    f0 = lambda v: "–" if v is None else f"{v:.0f}"
    bars("main-score.png", ranked + honorable + part, lambda s: s["jevbench_score"],
         lambda s, v: f"{v:.1f}   I {f0(ax4(s)['intelligence'])} · C {f0(ax4(s)['calibration'])} · S {f0(ax4(s)['speed'])} · K {f0(ax4(s)['cost'])}  ({cost(s)} / 1k decisions)",
         f"JevBench {RES['revision']} — JevBench Score",
         "Intelligence, Calibration, Speed, Cost — 25 % each, geometric mean: a weak axis pulls the score down hard. "
         f"{sum(RES['tiers'].values())} decisions incl. {n_hard} hard.",
         "K = Cost. Prices are US$ per 1,000 DECISIONS — not per 1,000 tokens. One decision is a whole question: its state, its rubric and its options.\n"
         + COST_EXAMPLE + "\n"
         "Latency of self-hosted and demo endpoints is adjusted ×2 (+0.15 s on our own servers) to approximate production load — an assumption; raw measurements in the repo.\n"
         "est. = hosted-provider list price for the same size class, or a flat plan's price at full use; announced = provider's published price, not yet charged.\n"
         + (RES["honorable_mentions"]["rule"].split(" Ranking it")[0] if RES.get("honorable_mentions") else ""))
    # four axes side by side, ranked systems only
    fig, axs = plt.subplots(1, 4, figsize=(16, 0.5 * len(ranked) + 2.6), facecolor=SURFACE, sharey=True)
    fig.subplots_adjust(left=0.2, right=0.99, wspace=0.08, top=1 - 1.05 / (0.5 * len(ranked) + 2.6), bottom=1.0 / (0.5 * len(ranked) + 2.6))
    ys = list(range(len(ranked)))[::-1]
    for ax, (k, t) in zip(axs, [("intelligence", "Intelligence"), ("calibration", "Calibration"), ("speed", "Speed (adjusted)"), ("cost", "Cost ($ per 1,000 decisions)")]):
        frame(ax)
        for y, s in zip(ys, ranked):
            v = s["axes"][k] or 0
            ax.barh(y, v, color=CLASS[s["class"]][0], height=0.66)
            ax.text(v + 1.5, y, f"{v:.0f}", va="center", fontsize=9.5, color=INK)
        ax.set_xlim(0, 115)
        ax.set_xticks([0, 50, 100])
        ax.set_title(t, fontsize=11.5, color=INK, loc="left")
    axs[0].set_yticks(ys, [name(s) for s in ranked])
    stamp(fig, f"JevBench {RES['revision']} — the four axes", "Each 0–100. The JevBench Score is their geometric mean.",
          "Cost is scored from US$ per 1,000 DECISIONS (a whole question each), never per 1,000 tokens. " + COST_EXAMPLE + "\n"
          "Speed: latency of self-hosted and demo endpoints adjusted ×2 (+0.15 s on our own servers) — an assumption, not a measurement.")
    legend(fig, {s["class"] for s in ranked})
    fig.savefig(OUT / "axes.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)
    def hard_acc(s):  # partial runs: accuracy over the items actually attempted
        h = s["hard"]
        return 100 * h["accuracy"] * h["n_items"] / h["n_attempted"] if h["coverage"] < 0.95 else 100 * h["accuracy"]

    def hard_label(s, v):
        h = s["hard"]
        v11 = [s["tiers"][t] for t in ("easy", "standard", "judge")]
        tail = f"(v1.1 tiers: {100 * sum(v11) / 3:.1f} %)" if None not in v11 else ""
        return f"{v:.1f} %   " + (f"of {h['n_attempted']} attempted" if h["coverage"] < 0.95 else tail)

    hrows = sorted([s for s in sys_ if s["hard"] and s["hard"]["n_attempted"]], key=lambda s: (not s["ranked"], s["partial"], -hard_acc(s)))
    bars("hard-tier.png", hrows, hard_acc, hard_label,
         f"JevBench {RES['revision']} — hard-tier accuracy",
         f"{n_hard} decisions: long multi-condition documents, trade-offs, ambiguous cases, traps, multi-hop, dates & numbers, answer judging",
         "Items written by Claude Opus 5 and GPT-5.6 Sol, cross-reviewed, frozen before any system ran. Failed or unparseable answers count as wrong.")
    crows = sorted([s for s in sys_ if s["calibration"]["score"] is not None], key=lambda s: (not s["ranked"], s["partial"], -s["calibration"]["score"]))
    bars("calibration.png", crows, lambda s: s["calibration"]["score"],
         lambda s, v: f"{v:.1f}   ECE {s['calibration']['ece_hard']:.3f}" + (f" · fidelity {s['calibration']['probability_fidelity']:.0f}" if s['calibration']['probability_fidelity'] is not None else ""),
         f"JevBench {RES['revision']} — Calibration (hard tier)",
         "Mean of (100 × (1 − ECE/0.5)) and probability fidelity (100 × (1 − total-variation distance to the exact gold distribution) on 20 probability items)",
         "Label-only systems (Needle 3) have no distribution and no calibration score (0 in the JevBench Score). Verbalised LLM probabilities and native model distributions are both scored as returned.")
    # heat table of hard-tier families
    hrows = [s for s in hrows if s["hard"]["coverage"] >= 0.95]  # unattempted items would read as wrong answers
    fams = sorted({f for s in hrows for f in s["hard"]["by_family"]})
    fig, ax = plt.subplots(figsize=(14, 0.5 * len(hrows) + 2.8), facecolor=SURFACE)
    fig.subplots_adjust(left=0.25, right=0.99, top=1 - 1.25 / (0.5 * len(hrows) + 2.8), bottom=0.9 / (0.5 * len(hrows) + 2.8))
    ax.set_facecolor(SURFACE)
    M = [[s["hard"]["by_family"][f]["accuracy"] * 100 for f in fams] for s in hrows]
    ax.imshow(M, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    for i, row in enumerate(M):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9.5, color="white" if v > 60 else INK)
    ax.set_xticks(range(len(fams)), [f"{f.replace('_', ' ')}\n(n={hrows[0]['hard']['by_family'][f]['n']})" for f in fams], fontsize=9)
    ax.set_yticks(range(len(hrows)), [name(s) for s in hrows])
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    stamp(fig, f"JevBench {RES['revision']} — hard tier by item family (accuracy %)", "Where the systems differ: dates & numbers and long policy documents separate them most",
          "Families with n ≤ 16 are small; read single cells with care.")
    fig.savefig(OUT / "hard-families.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print("charts ->", OUT)


if __name__ == "__main__":
    main()
