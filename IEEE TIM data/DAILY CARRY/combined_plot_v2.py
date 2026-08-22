"""
Standalone combined F1-vs-Threshold plot.

Uses the same estimator as LOO_CV_v3.py:
  - point estimate = pooled ratio F1 (counts summed first, then divided)
  - band          = cluster-robust 95% CI with the five held-out days as clusters

When several vapes are plotted together, their TP/FP/FN are summed *within* each
day, so the sampling unit stays the day and the interval never implies inference
across ENDS models.

Runs on its own with pandas / numpy / scipy / matplotlib installed.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")  # or "Qt5Agg"
import matplotlib as mpl
import matplotlib.pyplot as plt
from scipy import stats


def set_ieee_style():
    mpl.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.linewidth": 0.8,
        "grid.linewidth": 0.5,
        "figure.dpi": 200,
        "savefig.dpi": 600,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    })


# ----------------------------
# Metric Helpers
# ----------------------------
def f1_score(tp: float, fp: float, fn: float) -> float:
    denom = 2 * tp + fp + fn
    return 0.0 if denom == 0 else (2 * tp) / denom


def ratio_ci95(numerators, denominators):
    """
    Cluster-robust 95% CI for a ratio estimator R = sum(a_i) / sum(b_i):

        CI = t(0.975, n-1) * sqrt( n * SUM((a_i - R*b_i)^2)
                                   / ((n-1) * (SUM(b_i))^2) )

    This is the linearized (delta-method) variance of a ratio, with each
    cluster (here: a held-out day) as the sampling unit.
    """
    a = np.asarray(numerators, dtype=float)
    b = np.asarray(denominators, dtype=float)
    n = len(a)

    sum_b = b.sum()
    if sum_b == 0:
        return 0.0, 0.0

    ratio = a.sum() / sum_b

    if n < 2:
        return ratio, np.nan

    t_crit = stats.t.ppf(0.975, n - 1)
    resid_ss = np.sum((a - ratio * b) ** 2)
    ci95 = t_crit * np.sqrt(n * resid_ss / ((n - 1) * sum_b ** 2))

    return ratio, ci95


# ----------------------------
# Excel Parsing Helpers
# ----------------------------
def find_row(raw: pd.DataFrame, text: str) -> int:
    """Find the first row index where column 0 matches 'text'."""
    for r in range(len(raw)):
        if isinstance(raw.iat[r, 0], str) and raw.iat[r, 0].strip() == text:
            return r
    raise ValueError(f"Could not find row with first-column text: {text}")


def parse_threshold_day_table(raw: pd.DataFrame, header_row: int, col_start: int) -> pd.DataFrame:
    """
    Parses a table with layout:
      row: "Threshold", "Day1", "Day2", "Day3", "Day4", "Day5", ...
    starting at (header_row, col_start).
    Returns columns: Threshold, Day1..Day5
    """
    if str(raw.iat[header_row, col_start]).strip() != "Threshold":
        raise ValueError(
            f"Expected 'Threshold' at row {header_row}, col {col_start} "
            f"but found: {raw.iat[header_row, col_start]}"
        )

    day_cols = [col_start + i for i in range(1, 6)]
    out_rows = []
    r = header_row + 1

    while r < len(raw):
        thr = raw.iat[r, col_start]
        if pd.isna(thr):
            break

        # Stop if we hit next block header (string)
        if isinstance(thr, str):
            break

        days = []
        for c in day_cols:
            val = raw.iat[r, c]
            days.append(0 if pd.isna(val) else float(val))

        out_rows.append([float(thr)] + days)
        r += 1

    return pd.DataFrame(out_rows, columns=["Threshold", "Day1", "Day2", "Day3", "Day4", "Day5"])


def parse_threshold_session_fp(raw: pd.DataFrame, header_row: int, col_start: int,
                               name: str) -> pd.DataFrame:
    """
    Reads the 'Total FP' column of a puff-session block (col_start + 7).

    These false positives are recorded only as a 5-day total per block; the sheet
    has no per-day breakdown for them. Row scanning matches
    parse_threshold_day_table so the tables align on Threshold.
    """
    out_rows = []
    r = header_row + 1

    while r < len(raw):
        thr = raw.iat[r, col_start]
        if pd.isna(thr):
            break

        if isinstance(thr, str):
            break

        val = raw.iat[r, col_start + 7]
        out_rows.append([float(thr), 0.0 if pd.isna(val) else float(val)])
        r += 1

    return pd.DataFrame(out_rows, columns=["Threshold", name])


def build_daywise_counts_for_vape(raw: pd.DataFrame, vape_name: str) -> pd.DataFrame:
    """
    Builds per-threshold, per-day TP/FP/FN for a given vape block.
    Assumes the layout in Book1.xlsx:
      - 1s table at col 0
      - 2s table at col 9
      - 3s table at col 18
      - False positives table at col 28
    FP combines the per-day pocket-carry table with the puff-session 'Total FP'
    of each duration block (cols 7 / 16 / 25).
    """
    vape_row = find_row(raw, vape_name)
    # The "Threshold / Day1..Day5" header row is vape_row + 2
    header_row = vape_row + 2

    tp_1s = parse_threshold_day_table(raw, header_row=header_row, col_start=0)
    tp_2s = parse_threshold_day_table(raw, header_row=header_row, col_start=9)
    tp_3s = parse_threshold_day_table(raw, header_row=header_row, col_start=18)
    fp_tbl = parse_threshold_day_table(raw, header_row=header_row, col_start=28)

    fp_1s = parse_threshold_session_fp(raw, header_row=header_row, col_start=0, name="SessionFP_1s")
    fp_2s = parse_threshold_session_fp(raw, header_row=header_row, col_start=9, name="SessionFP_2s")
    fp_3s = parse_threshold_session_fp(raw, header_row=header_row, col_start=18, name="SessionFP_3s")

    df = tp_1s.rename(columns={f"Day{i}": f"TP1_Day{i}" for i in range(1, 6)})
    df = df.merge(tp_2s.rename(columns={f"Day{i}": f"TP2_Day{i}" for i in range(1, 6)}),
                  on="Threshold", how="inner")
    df = df.merge(tp_3s.rename(columns={f"Day{i}": f"TP3_Day{i}" for i in range(1, 6)}),
                  on="Threshold", how="inner")
    df = df.merge(fp_tbl.rename(columns={f"Day{i}": f"FP_Day{i}" for i in range(1, 6)}),
                  on="Threshold", how="inner")

    for fp_block in (fp_1s, fp_2s, fp_3s):
        df = df.merge(fp_block, on="Threshold", how="inner")

    # Total false positives recorded during the puff sessions. The sheet stores
    # these per block as a 5-day total only, so they are spread evenly over the
    # five days: the pooled totals still match the sheet's own 'Total FP'
    # column, and the puff-session FPs add no between-day variance.
    df["SessionFP_Total"] = df["SessionFP_1s"] + df["SessionFP_2s"] + df["SessionFP_3s"]

    for i in range(1, 6):
        df[f"TP_Day{i}"] = df[f"TP1_Day{i}"] + df[f"TP2_Day{i}"] + df[f"TP3_Day{i}"]

        # Pocket-carry false positives (per day) + puff-session share
        df[f"FP_Day{i}"] = df[f"FP_Day{i}"] + df["SessionFP_Total"] / 5.0

        # Expected 90 puffs/day (30 of each duration)
        df[f"FN_Day{i}"] = 90.0 - df[f"TP_Day{i}"]
        df[f"FN_Day{i}"] = df[f"FN_Day{i}"].clip(lower=0)

    return df.sort_values("Threshold").reset_index(drop=True)


# ----------------------------
# Day-clustered counts across vapes
# ----------------------------
def pool_daywise_counts(raw: pd.DataFrame, vapes: list):
    """
    Returns (thresholds, tp, fp, fn) where tp/fp/fn are arrays of shape
    (n_thresholds, 5): counts summed across the given vapes within each day.

    Summing within the day is what keeps the day as the sampling unit, so the
    resulting interval reflects day-to-day variability only.
    """
    thresholds = None
    tp = fp = fn = None

    for vape in vapes:
        df_daywise = build_daywise_counts_for_vape(raw, vape)
        vape_thresholds = df_daywise["Threshold"].to_numpy(dtype=float)

        if thresholds is None:
            thresholds = vape_thresholds
            shape = (len(thresholds), 5)
            tp, fp, fn = np.zeros(shape), np.zeros(shape), np.zeros(shape)
        elif len(vape_thresholds) != len(thresholds) or not np.allclose(vape_thresholds, thresholds):
            raise ValueError("Threshold grids do not match across vapes.")

        for d in range(1, 6):
            tp[:, d - 1] += df_daywise[f"TP_Day{d}"].to_numpy(dtype=float)
            fp[:, d - 1] += df_daywise[f"FP_Day{d}"].to_numpy(dtype=float)
            fn[:, d - 1] += df_daywise[f"FN_Day{d}"].to_numpy(dtype=float)

    return thresholds, tp, fp, fn


def f1_curve_with_band(raw: pd.DataFrame, vapes: list, band: str = "ci95", clamp: bool = True):
    """
    Pooled ratio F1 per threshold, with a band across the five held-out days.

    band = "ci95" -> cluster-robust 95% CI half-width (same estimator as LOO_CV_v3)
    band = "sd"   -> SD of the five per-day pooled F1 values (descriptive only)
    """
    if band not in ("ci95", "sd"):
        raise ValueError("band must be 'ci95' or 'sd'")

    thresholds, tp, fp, fn = pool_daywise_counts(raw, vapes)

    f1 = np.zeros(len(thresholds))
    half = np.zeros(len(thresholds))

    for i in range(len(thresholds)):
        if band == "ci95":
            f1[i], half[i] = ratio_ci95(2 * tp[i], 2 * tp[i] + fp[i] + fn[i])
        else:
            f1[i] = f1_score(tp[i].sum(), fp[i].sum(), fn[i].sum())
            per_day = np.array([f1_score(tp[i, d], fp[i, d], fn[i, d]) for d in range(5)])
            half[i] = per_day.std(ddof=1)

    lower = f1 - half
    upper = f1 + half

    if clamp:
        lower = np.clip(lower, 0.0, 1.0)
        upper = np.clip(upper, 0.0, 1.0)

    return thresholds, f1, lower, upper


# ----------------------------
# Plot
# ----------------------------
def plot_f1_vs_threshold_with_band(
        raw: pd.DataFrame,
        vapes: list,
        title: str,
        band: str = "ci95",
        clamp: bool = True,
        ieee_single_col: bool = True,
        end_Lim: float = 3.2,
) -> None:
    """
    x-axis: Threshold (0.0..3.2, step 0.2 as available in the sheet)
    y-axis: Pooled ratio F1 across the five held-out days
    shaded: cluster-robust 95% CI (or SD across days)

    Each cluster = one held-out day. If several vapes are given, their counts are
    summed within each day, so there are always five clusters.
    """
    x, f1, lower, upper = f1_curve_with_band(raw, vapes, band=band, clamp=clamp)
    band_label = "95% CI" if band == "ci95" else "SD across days"

    if ieee_single_col:
        plt.figure(figsize=(3.5, 2.6), dpi=200)
        lw, ms = 1.2, 4
        lab_fs, tick_fs = 9, 8
    else:
        plt.figure(figsize=(7, 4), dpi=200)
        lw, ms = 1.5, 5
        lab_fs, tick_fs = 11, 10

    plt.plot(x, f1, marker="o", linewidth=lw, markersize=ms, label="F1")
    plt.fill_between(x, lower, upper, alpha=0.20, label=band_label)

    plt.xlim(0.0, end_Lim)
    plt.ylim(0.0, 1.0)

    # Keep data at 0.2s increments; label the axis every 0.4s to reduce clutter
    plt.xticks(np.arange(0.0, end_Lim + 1e-9, 0.4))
    plt.yticks(np.arange(0.0, 1.0 + 1e-9, 0.25))

    plt.grid(True, linewidth=0.5, alpha=0.4)
    plt.xlabel("Detection threshold (seconds)", fontsize=lab_fs)
    plt.ylabel("F1 Score", fontsize=lab_fs)
    plt.title(title, fontsize=lab_fs)

    plt.tick_params(axis="both", labelsize=tick_fs)
    for spine in plt.gca().spines.values():
        spine.set_linewidth(0.8)

    plt.legend(loc="lower left", frameon=False, fontsize=tick_fs)
    plt.tight_layout()
    plt.show(block=True)


def find_workbook(filename: str = "Book1.xlsx") -> Path:
    codebase_dir = Path(__file__).resolve().parent
    matches = sorted(codebase_dir.rglob(filename))

    if not matches:
        raise FileNotFoundError(
            f"Could not find {filename!r} under {codebase_dir}. "
            "Place the workbook inside the codebase folder and run again."
        )

    return matches[0]


if __name__ == "__main__":
    xlsx_path = find_workbook()
    raw = pd.read_excel(xlsx_path, sheet_name=0, header=None)

    vapes = [
        "Geekbar With Thermistor",
        "NJOY Without Thermistor",
    ]

    set_ieee_style()

    plot_f1_vs_threshold_with_band(
        raw=raw,
        vapes=vapes,
        title="Combined: F1 vs Threshold",
        band="ci95",
        clamp=True,
        ieee_single_col=True,
        end_Lim=3.2,
    )
