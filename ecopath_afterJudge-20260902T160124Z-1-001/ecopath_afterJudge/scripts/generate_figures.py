"""
generate_figures.py  –  EcoPath Research Paper Figure Generator
================================================================
Generates all publication-ready figures for the EcoPath paper:
  Fig 1 – Dataset Overview (IUCN distribution, split sizes)
  Fig 2 – Training Loss Curve
  Fig 3 – Main Evaluation Results (Base vs Fine-Tuned)
  Fig 4 – Per-Species JSON Validity Heatmap
  Fig 5 – Output Length Analysis
  Fig 6 – BERTScore Distribution (FT vs Base)
  Fig 7 – Combined Summary Dashboard

Usage (Colab):
  !python /content/drive/MyDrive/ecopath/scripts/generate_figures.py
"""

from __future__ import annotations
import json, re, sys, warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.ticker as mticker

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path("/content/drive/MyDrive/ecopath/extinction_risk/ecopath_gemini100_run1")
SPLITS_DIR = BASE_DIR / "splits"
OUTPUT_DIR = BASE_DIR / "figures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_PATH = BASE_DIR / "eval_results.jsonl"
REPORT_PATH  = BASE_DIR / "eval_report.json"

TRAINER_STATE_CANDIDATES = [
    BASE_DIR / "final" / "trainer_state.json",
    BASE_DIR / "trainer_state.json",
    BASE_DIR / "checkpoints" / "trainer_state.json",
]

# ── Style ────────────────────────────────────────────────────────────────────
C_BASE  = "#E07B54"
C_FT    = "#3A86FF"
C_GREEN = "#06D6A0"
C_DARK  = "#1A1A2E"
C_LIGHT = "#F0F4FF"

IUCN_COLORS = {
    "Least Concern":        "#60B347",
    "LC":                   "#60B347",
    "Near Threatened":      "#CCE226",
    "NT":                   "#CCE226",
    "Vulnerable":           "#F9A825",
    "VU":                   "#F9A825",
    "Endangered":           "#E65100",
    "EN":                   "#E65100",
    "Critically Endangered":"#B71C1C",
    "CR":                   "#B71C1C",
    "Data Deficient":       "#90A4AE",
    "DD":                   "#90A4AE",
    "Unknown":              "#BDBDBD",
}

IUCN_ORDER = ["Least Concern","Near Threatened","Vulnerable",
              "Endangered","Critically Endangered","Data Deficient","Unknown"]

plt.rcParams.update({
    "font.family":       "DejaVu Serif",
    "font.size":         11,
    "axes.titlesize":    13,
    "axes.titleweight":  "bold",
    "axes.labelsize":    11,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "figure.facecolor":  "white",
    "axes.facecolor":    C_LIGHT,
    "grid.color":        "white",
    "grid.linewidth":    1.2,
    "savefig.dpi":       300,
    "savefig.bbox":      "tight",
    "savefig.facecolor": "white",
})

# ── Helpers ──────────────────────────────────────────────────────────────────
def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

def count_words(text: str) -> int:
    return len(text.split()) if text else 0

def norm_iucn(s) -> str:
    if not s:
        return "Unknown"
    mapping = {
        "leastconcern": "Least Concern", "lc": "Least Concern",
        "nearthreatened": "Near Threatened", "nt": "Near Threatened",
        "vulnerable": "Vulnerable", "vu": "Vulnerable",
        "endangered": "Endangered", "en": "Endangered",
        "criticallyendangered": "Critically Endangered", "cr": "Critically Endangered",
        "datadeficient": "Data Deficient", "dd": "Data Deficient",
    }
    key = re.sub(r"[^a-z]", "", s.lower())
    return mapping.get(key, s.strip().title())

def is_valid_json(text: str):
    if not text:
        return False, None
    cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", text.strip())
    try:
        return True, json.loads(cleaned)
    except Exception:
        m = re.search(r"(\{[\s\S]*\})", cleaned)
        if m:
            try:
                return True, json.loads(m.group(1))
            except Exception:
                pass
    return False, None

def check_schema(parsed) -> bool:
    REQUIRED = {"species","current_conservation_status","key_threats",
                "survivability_assessment","mitigation_actions","sources"}
    if not isinstance(parsed, dict):
        return False
    draft = parsed.get("decision_support_draft")
    target = draft if isinstance(draft, dict) else parsed
    return all(k in target for k in REQUIRED)

def save(fig, name: str):
    p = OUTPUT_DIR / name
    fig.savefig(p)
    print(f"  Saved -> {p}")
    plt.close(fig)

# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading data...")
train_records = load_jsonl(SPLITS_DIR / "train.jsonl")
eval_records  = load_jsonl(SPLITS_DIR / "eval.jsonl")
results       = load_jsonl(RESULTS_PATH)
report        = json.loads(REPORT_PATH.read_text(encoding="utf-8")) if REPORT_PATH.exists() else {}

trainer_state = None
for p in TRAINER_STATE_CANDIDATES:
    if p.exists():
        trainer_state = json.loads(p.read_text(encoding="utf-8"))
        print(f"  Found trainer_state at {p}")
        break

print(f"  train={len(train_records)}  eval={len(eval_records)}  results={len(results)}")

# ── Pre-compute metrics ───────────────────────────────────────────────────────
base_json_valid, ft_json_valid = [], []
base_schema_ok,  ft_schema_ok  = [], []
species_names = []

for r in results:
    species_names.append(r.get("species", "?"))
    bv, bp = is_valid_json(r.get("base_model_output", ""))
    fv, fp = is_valid_json(r.get("ft_model_output", ""))
    base_json_valid.append(bv)
    ft_json_valid.append(fv)
    base_schema_ok.append(check_schema(bp) if bv else False)
    ft_schema_ok.append(check_schema(fp) if fv else False)

n = len(results) or 1
base_lengths = [count_words(r.get("base_model_output", "")) for r in results]
ft_lengths   = [count_words(r.get("ft_model_output",   "")) for r in results]
base_v = [100*sum(base_json_valid)/n, 100*sum(base_schema_ok)/n]
ft_v   = [100*sum(ft_json_valid)/n,   100*sum(ft_schema_ok)/n]

# ═══════════════════════════════════════════════════════════════════════════════
# FIG 1 – Dataset Overview
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[1/7] Dataset Overview...")

all_records = train_records + eval_records
iucn_counts: dict[str, int] = {}
for r in all_records:
    label = norm_iucn(r.get("iucn_status") or r.get("iucn_status_ground_truth"))
    iucn_counts[label] = iucn_counts.get(label, 0) + 1

labels  = [l for l in IUCN_ORDER if l in iucn_counts]
counts  = [iucn_counts[l] for l in labels]
colors  = [IUCN_COLORS.get(l, "#BDBDBD") for l in labels]

fig, axes = plt.subplots(1, 3, figsize=(16, 5))
fig.suptitle("EcoPath Dataset Overview", fontsize=16, fontweight="bold", y=1.02)

ax = axes[0]
bars = ax.barh(labels, counts, color=colors, edgecolor="white", linewidth=0.8)
ax.set_xlabel("Number of Species")
ax.set_title("IUCN Status Distribution")
ax.set_xlim(0, max(counts)*1.3 if counts else 10)
for bar, count in zip(bars, counts):
    ax.text(bar.get_width()+0.1, bar.get_y()+bar.get_height()/2,
            str(count), va="center", fontweight="bold")
ax.invert_yaxis()

ax = axes[1]
split_sizes  = [len(train_records), len(eval_records)]
split_colors = [C_FT, C_BASE]
if any(split_sizes):
    wedges, texts, autos = ax.pie(
        split_sizes, labels=["Training","Evaluation"], colors=split_colors,
        autopct="%1.0f%%", startangle=90,
        wedgeprops={"edgecolor":"white","linewidth":2})
    for at in autos:
        at.set_fontweight("bold"); at.set_fontsize(13)
ax.set_title(f"Train / Eval Split\n(Total: {len(all_records)} species)")
ax.set_facecolor("white")

ax = axes[2]
ax.axis("off")
eval_iucn = [(r.get("species", r.get("common_name","?")),
              norm_iucn(r.get("iucn_status") or r.get("iucn_status_ground_truth")))
             for r in eval_records]
if eval_iucn:
    tbl = ax.table(
        cellText=[[s,i] for s,i in eval_iucn],
        colLabels=["Species","IUCN Status"],
        cellLoc="left", loc="center",
    )
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1, 1.3)
    for (r,c), cell in tbl.get_celld().items():
        cell.set_edgecolor("white")
        if r == 0:
            cell.set_facecolor(C_DARK)
            cell.set_text_props(color="white", fontweight="bold")
ax.set_title("Evaluation Set Species", fontweight="bold", pad=10)

plt.tight_layout()
save(fig, "fig1_dataset_overview.png")

# ═══════════════════════════════════════════════════════════════════════════════
# FIG 2 – Training Loss
# ═══════════════════════════════════════════════════════════════════════════════
print("[2/7] Training Loss Curve...")
fig, ax = plt.subplots(figsize=(10, 5))
fig.suptitle("Fine-Tuning Training Loss (Qwen2.5-7B-Instruct)", fontsize=15, fontweight="bold")

if trainer_state and "log_history" in trainer_state:
    log = trainer_state["log_history"]
    ts = [e["step"] for e in log if "loss" in e]
    tl = [e["loss"] for e in log if "loss" in e]
    es = [e["step"] for e in log if "eval_loss" in e]
    el = [e["eval_loss"] for e in log if "eval_loss" in e]

    ax.plot(ts, tl, color=C_FT, linewidth=2, label="Training Loss", zorder=3)
    ax.fill_between(ts, tl, alpha=0.15, color=C_FT)
    if es:
        ax.plot(es, el, color=C_BASE, linewidth=2, linestyle="--",
                marker="o", markersize=5, label="Validation Loss", zorder=4)
    if tl:
        ax.annotate(f"Final: {tl[-1]:.3f}",
                    xy=(ts[-1], tl[-1]), xytext=(-60, 15),
                    textcoords="offset points",
                    arrowprops=dict(arrowstyle="->", color=C_DARK),
                    fontsize=10, fontweight="bold")
    ax.set_xlabel("Training Step"); ax.set_ylabel("Loss")
    ax.legend(frameon=True); ax.grid(True, alpha=0.5)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
else:
    ax.text(0.5, 0.5,
            "trainer_state.json not found.\nEnsure it is saved during training.",
            transform=ax.transAxes, ha="center", va="center", fontsize=13,
            color="#666666",
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF9C4", edgecolor="#F9A825"))

plt.tight_layout()
save(fig, "fig2_training_loss.png")

# ═══════════════════════════════════════════════════════════════════════════════
# FIG 3 – Main Results
# ═══════════════════════════════════════════════════════════════════════════════
print("[3/7] Main Evaluation Results...")
fig, axes = plt.subplots(1, 2, figsize=(12, 6))
fig.suptitle("EcoPath: Base Model vs Fine-Tuned Evaluation Results",
             fontsize=15, fontweight="bold")

ax = axes[0]
x = np.arange(2); w = 0.32
metric_labels = ["JSON\nValidity", "Schema\nCompliance"]
b1 = ax.bar(x-w/2, base_v, w, color=C_BASE, label="Base Model",    edgecolor="white", zorder=3)
b2 = ax.bar(x+w/2, ft_v,   w, color=C_FT,   label="Fine-Tuned",    edgecolor="white", zorder=3)
for bar in b1:
    v=bar.get_height(); ax.text(bar.get_x()+bar.get_width()/2, v+1.5, f"{v:.0f}%",
        ha="center", fontsize=11, fontweight="bold", color=C_BASE)
for bar in b2:
    v=bar.get_height(); ax.text(bar.get_x()+bar.get_width()/2, v+1.5, f"{v:.0f}%",
        ha="center", fontsize=11, fontweight="bold", color=C_FT)
ax.set_xticks(x); ax.set_xticklabels(metric_labels, fontsize=12)
ax.set_ylabel("Score (%)"); ax.set_ylim(0, 120)
ax.set_title("Structural Quality Metrics")
ax.legend(frameon=True); ax.grid(True, axis="y", alpha=0.5)

ax2 = axes[1]
ax2.set_facecolor(C_LIGHT); ax2.set_xlim(0,1); ax2.set_ylim(0,1); ax2.axis("off")
ax2.set_title("Improvement Summary", fontweight="bold")
entries = [("JSON Validity",base_v[0],ft_v[0]),("Schema Compliance",base_v[1],ft_v[1])]
for i,(name,bv,fv) in enumerate(entries):
    y = 0.72 - i*0.38
    delta = fv - bv
    sign  = "+" if delta >= 0 else ""
    color = C_GREEN if delta >= 0 else C_BASE
    ax2.text(0.05, y+0.08, name, fontsize=13, fontweight="bold", color=C_DARK,
             transform=ax2.transAxes)
    ax2.text(0.05, y,      f"Base: {bv:.0f}%",       fontsize=11, color=C_BASE, transform=ax2.transAxes)
    ax2.text(0.05, y-0.09, f"Fine-Tuned: {fv:.0f}%", fontsize=11, color=C_FT,   transform=ax2.transAxes)
    ax2.text(0.75, y-0.01, f"{sign}{delta:.0f}pp",
             fontsize=24, fontweight="bold", color=color, ha="center", va="center",
             transform=ax2.transAxes,
             bbox=dict(boxstyle="round,pad=0.4", facecolor=color, alpha=0.15, edgecolor=color))
ax2.text(0.5, 0.05, f"n = {n} species", fontsize=10, color="#888888",
         ha="center", transform=ax2.transAxes)

plt.tight_layout()
save(fig, "fig3_main_results.png")

# ═══════════════════════════════════════════════════════════════════════════════
# FIG 4 – Per-Species Heatmap
# ═══════════════════════════════════════════════════════════════════════════════
print("[4/7] Per-Species Heatmap...")
matrix = np.array([
    [int(base_json_valid[i]), int(base_schema_ok[i]),
     int(ft_json_valid[i]),   int(ft_schema_ok[i])]
    for i in range(len(results))
], dtype=float)

fig, ax = plt.subplots(figsize=(9, max(5, len(results)*0.45+1.5)))
fig.suptitle("Per-Species Results: Base vs Fine-Tuned", fontsize=15, fontweight="bold")

cmap = LinearSegmentedColormap.from_list("ecopath", ["#FFEBEE","#43A047"])
ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)
col_labels = ["Base\nJSON Valid","Base\nSchema OK","FT\nJSON Valid","FT\nSchema OK"]
ax.set_xticks(range(4)); ax.set_xticklabels(col_labels, fontsize=10)
ax.set_yticks(range(len(species_names))); ax.set_yticklabels(species_names, fontsize=9)
ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False)
for i in range(len(species_names)):
    for j in range(4):
        val = matrix[i,j]
        ax.text(j, i, "YES" if val==1 else "NO", ha="center", va="center",
                fontsize=9, fontweight="bold",
                color="white" if val==1 else "#C62828")
ax.axvline(1.5, color="white", linewidth=3)

plt.tight_layout()
save(fig, "fig4_per_species_heatmap.png")

# ═══════════════════════════════════════════════════════════════════════════════
# FIG 5 – Output Length
# ═══════════════════════════════════════════════════════════════════════════════
print("[5/7] Output Length Analysis...")
short_names = [" ".join(s.split()[:2]) for s in species_names]

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Output Length Analysis: Base vs Fine-Tuned", fontsize=15, fontweight="bold")

ax = axes[0]
x = np.arange(len(species_names)); w = 0.38
ax.bar(x-w/2, base_lengths, w, color=C_BASE, label="Base Model", alpha=0.85, zorder=3)
ax.bar(x+w/2, ft_lengths,   w, color=C_FT,   label="Fine-Tuned", alpha=0.85, zorder=3)
ax.set_xticks(x)
ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=7.5)
ax.set_ylabel("Word Count"); ax.set_title("Words per Output")
ax.legend(); ax.grid(True, axis="y", alpha=0.5)

ax2 = axes[1]
if base_lengths and ft_lengths:
    bp = ax2.boxplot([base_lengths, ft_lengths], labels=["Base Model","Fine-Tuned"],
                     patch_artist=True,
                     medianprops=dict(color=C_DARK, linewidth=2.5))
    bp["boxes"][0].set_facecolor(C_BASE+"99")
    bp["boxes"][1].set_facecolor(C_FT+"99")
    for i, vals in enumerate([base_lengths, ft_lengths], 1):
        ax2.text(i, np.mean(vals)+5, f"mean={np.mean(vals):.0f}",
                 ha="center", fontsize=9, fontweight="bold")
ax2.set_ylabel("Word Count"); ax2.set_title(f"Distribution (n={n})")
ax2.grid(True, axis="y", alpha=0.5)

plt.tight_layout()
save(fig, "fig5_output_length.png")

# ═══════════════════════════════════════════════════════════════════════════════
# FIG 6 – BERTScore
# ═══════════════════════════════════════════════════════════════════════════════
print("[6/7] BERTScore...")
try:
    from bert_score import score as bert_score_fn
    refs = [r.get("base_model_output","") or "" for r in results]
    hyps = [r.get("ft_model_output",  "") or "" for r in results]
    _, _, F1 = bert_score_fn(hyps, refs, lang="en", verbose=False)
    f1_vals = F1.numpy().tolist()

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("BERTScore F1: Fine-Tuned vs Base Outputs", fontsize=15, fontweight="bold")

    ax = axes[0]
    bar_colors = [C_GREEN if v>=0.85 else C_FT if v>=0.75 else C_BASE for v in f1_vals]
    ax.bar(range(len(f1_vals)), f1_vals, color=bar_colors, edgecolor="white", zorder=3)
    ax.axhline(np.mean(f1_vals), color=C_DARK, linewidth=2, linestyle="--",
               label=f"Mean F1 = {np.mean(f1_vals):.3f}")
    ax.set_xticks(range(len(short_names)))
    ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=7.5)
    ax.set_ylabel("BERTScore F1"); ax.set_ylim(0.5, 1.0)
    ax.set_title("Per-Species BERTScore F1"); ax.legend(); ax.grid(True, axis="y", alpha=0.5)

    ax2 = axes[1]
    ax2.hist(f1_vals, bins=8, color=C_FT, edgecolor="white", alpha=0.85, zorder=3)
    ax2.axvline(np.mean(f1_vals), color=C_DARK, linewidth=2.5, linestyle="--",
                label=f"Mean = {np.mean(f1_vals):.3f}")
    ax2.set_xlabel("BERTScore F1"); ax2.set_ylabel("Count")
    ax2.set_title("F1 Distribution"); ax2.legend(); ax2.grid(True, axis="y", alpha=0.5)

    plt.tight_layout()
    save(fig, "fig6_bertscore.png")
except ImportError:
    print("  bert-score not installed — skipping Fig 6. Run: pip install bert-score")

# ═══════════════════════════════════════════════════════════════════════════════
# FIG 7 – Summary Dashboard
# ═══════════════════════════════════════════════════════════════════════════════
print("[7/7] Summary Dashboard...")
fig = plt.figure(figsize=(16, 10))
fig.patch.set_facecolor("white")
gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.38)
fig.suptitle("EcoPath: Fine-Tuning Qwen2.5-7B-Instruct for Conservation Decision Support",
             fontsize=14, fontweight="bold", y=1.01)

# A – bar chart
ax_a = fig.add_subplot(gs[0,0])
x_a = np.arange(2); w_a = 0.32
ax_a.bar(x_a-w_a/2, base_v, w_a, color=C_BASE, label="Base",       zorder=3)
ax_a.bar(x_a+w_a/2, ft_v,   w_a, color=C_FT,   label="Fine-Tuned", zorder=3)
ax_a.set_xticks(x_a); ax_a.set_xticklabels(["JSON\nValidity","Schema\nCompliance"], fontsize=9)
ax_a.set_ylim(0,120); ax_a.set_ylabel("Score (%)"); ax_a.set_title("(A) Structural Metrics")
ax_a.legend(fontsize=8); ax_a.grid(True, axis="y", alpha=0.5)
for i,(bv,fv) in enumerate(zip(base_v,ft_v)):
    ax_a.text(i-w_a/2, bv+2, f"{bv:.0f}%", ha="center", fontsize=9, color=C_BASE, fontweight="bold")
    ax_a.text(i+w_a/2, fv+2, f"{fv:.0f}%", ha="center", fontsize=9, color=C_FT,   fontweight="bold")

# B – IUCN
ax_b = fig.add_subplot(gs[0,1])
b_labels = [l for l in IUCN_ORDER if l in iucn_counts]
ax_b.barh(b_labels, [iucn_counts[l] for l in b_labels],
          color=[IUCN_COLORS[l] for l in b_labels], edgecolor="white", zorder=3)
ax_b.set_xlabel("Count"); ax_b.set_title("(B) IUCN Distribution")
ax_b.invert_yaxis(); ax_b.grid(True, axis="x", alpha=0.5)

# C – box plot
ax_c = fig.add_subplot(gs[0,2])
if base_lengths and ft_lengths:
    bp2 = ax_c.boxplot([base_lengths, ft_lengths], labels=["Base","Fine-Tuned"],
                       patch_artist=True, medianprops=dict(color=C_DARK, linewidth=2))
    bp2["boxes"][0].set_facecolor(C_BASE+"99")
    bp2["boxes"][1].set_facecolor(C_FT+"99")
ax_c.set_ylabel("Word Count"); ax_c.set_title("(C) Output Lengths")
ax_c.grid(True, axis="y", alpha=0.5)

# D – training loss
ax_d = fig.add_subplot(gs[1,0:2])
if trainer_state and "log_history" in trainer_state:
    log = trainer_state["log_history"]
    ts = [e["step"] for e in log if "loss" in e]
    tl = [e["loss"] for e in log if "loss" in e]
    ax_d.plot(ts, tl, color=C_FT, linewidth=2, label="Train Loss", zorder=3)
    ax_d.fill_between(ts, tl, alpha=0.15, color=C_FT)
    ax_d.set_xlabel("Step"); ax_d.set_ylabel("Loss")
    ax_d.set_title("(D) Training Loss Curve"); ax_d.legend(); ax_d.grid(True, alpha=0.5)
else:
    ax_d.text(0.5, 0.5, "(D) Training Loss Curve\n(trainer_state.json not found)",
              ha="center", va="center", transform=ax_d.transAxes, fontsize=12, color="#888")
    ax_d.set_xlim(0,1); ax_d.set_ylim(0,1)

# E – summary table
ax_e = fig.add_subplot(gs[1,2])
ax_e.axis("off")
table_rows = [
    ["Metric",             "Base",                     "Fine-Tuned"],
    ["JSON Validity",      f"{base_v[0]:.0f}%",        f"{ft_v[0]:.0f}%"],
    ["Schema Compliance",  f"{base_v[1]:.0f}%",        f"{ft_v[1]:.0f}%"],
    ["Avg Output (words)", f"{np.mean(base_lengths):.0f}", f"{np.mean(ft_lengths):.0f}"],
    ["Eval Samples",       str(n),                     str(n)],
]
tbl_e = ax_e.table(cellText=table_rows[1:], colLabels=table_rows[0],
                   cellLoc="center", loc="center")
tbl_e.auto_set_font_size(False); tbl_e.set_fontsize(9); tbl_e.scale(1.1, 1.8)
for (r,c), cell in tbl_e.get_celld().items():
    cell.set_edgecolor("#DDDDDD")
    if r == 0:
        cell.set_facecolor(C_DARK)
        cell.set_text_props(color="white", fontweight="bold")
    elif c == 2:
        cell.set_facecolor(C_FT+"22")
    else:
        cell.set_facecolor("#FAFAFA")
ax_e.set_title("(E) Results Summary", fontweight="bold", pad=8)

save(fig, "fig7_summary_dashboard.png")

# ── Done ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"  All figures saved to: {OUTPUT_DIR}")
print(f"{'='*55}")
for f in sorted(OUTPUT_DIR.glob("fig*.png")):
    print(f"  {f.name}")
