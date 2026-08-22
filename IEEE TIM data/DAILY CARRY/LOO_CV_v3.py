"""
Leave-one-day-out threshold selection with pooled ratio metrics
and cluster-robust 95% confidence intervals (held-out folds as clusters).
"""

from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib as mpl
from scipy import stats


# ----------------------------
# Paths
# ----------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_PATH = SCRIPT_DIR / "Book1.xlsx"


# ----------------------------
# IEEE Plot Style
# ----------------------------
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
def precision_score(tp, fp):
    denom = tp + fp
    return 0.0 if denom == 0 else tp / denom


def recall_score(tp, fn):
    denom = tp + fn
    return 0.0 if denom == 0 else tp / denom


def f1_score(tp, fp, fn):
    denom = 2 * tp + fp + fn
    return 0.0 if denom == 0 else (2 * tp) / denom


def ratio_ci95(numerators, denominators):
    """
    Cluster-robust 95% CI for a ratio estimator R = sum(a_i) / sum(b_i):

        CI = t(0.975, n-1) * sqrt( n * SUM((a_i - R*b_i)^2)
                                   / ((n-1) * (SUM(b_i))^2) )

    This is the linearized (delta-method) variance of a ratio, with each
    cluster (here: a held-out fold) as the sampling unit.
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


def prf_with_cluster_ci95(tp, fp, fn):
    """Precision / Recall / F1 with cluster-robust 95% CI, from per-cluster counts."""
    tp = np.asarray(tp, dtype=float)
    fp = np.asarray(fp, dtype=float)
    fn = np.asarray(fn, dtype=float)

    return {
        "precision": ratio_ci95(tp, tp + fp),
        "recall": ratio_ci95(tp, tp + fn),
        "f1": ratio_ci95(2 * tp, 2 * tp + fp + fn),
    }


def print_cluster_ci95(res, title):
    print("\n" + title)
    for key, label in (("precision", "Precision"),
                       ("recall", "Recall   "),
                       ("f1", "F1 Score ")):
        value, ci = res[key]
        lower = max(0.0, value - ci)
        upper = min(1.0, value + ci)
        print(f"{label} = {value:.4f}  95% CI [{lower:.4f}, {upper:.4f}]")


# ----------------------------
# Excel Parsing Helpers
# ----------------------------
def find_row(raw: pd.DataFrame, text: str) -> int:
    for r in range(len(raw)):
        if isinstance(raw.iat[r, 0], str) and raw.iat[r, 0].strip() == text:
            return r
    raise ValueError(f"Could not find row with first-column text: {text}")


def parse_threshold_day_table(raw: pd.DataFrame, header_row: int, col_start: int) -> pd.DataFrame:
    if str(raw.iat[header_row, col_start]).strip() != "Threshold":
        raise ValueError(
            f"Expected 'Threshold' at row {header_row}, col {col_start}, "
            f"but found: {raw.iat[header_row, col_start]}"
        )

    day_cols = [col_start + i for i in range(1, 6)]
    out_rows = []
    r = header_row + 1

    while r < len(raw):
        threshold = raw.iat[r, col_start]

        if pd.isna(threshold):
            break

        if isinstance(threshold, str):
            break

        day_values = []
        for c in day_cols:
            val = raw.iat[r, c]
            day_values.append(0 if pd.isna(val) else float(val))

        out_rows.append([float(threshold)] + day_values)
        r += 1

    return pd.DataFrame(
        out_rows,
        columns=["Threshold", "Day1", "Day2", "Day3", "Day4", "Day5"]
    )


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
        threshold = raw.iat[r, col_start]

        if pd.isna(threshold):
            break

        if isinstance(threshold, str):
            break

        val = raw.iat[r, col_start + 7]
        out_rows.append([float(threshold), 0.0 if pd.isna(val) else float(val)])
        r += 1

    return pd.DataFrame(out_rows, columns=["Threshold", name])


def build_daywise_counts_for_vape(raw: pd.DataFrame, vape_name: str) -> pd.DataFrame:
    vape_row = find_row(raw, vape_name)
    header_row = vape_row + 2

    tp_1s = parse_threshold_day_table(raw, header_row, col_start=0)
    tp_2s = parse_threshold_day_table(raw, header_row, col_start=9)
    tp_3s = parse_threshold_day_table(raw, header_row, col_start=18)
    fp_tbl = parse_threshold_day_table(raw, header_row, col_start=28)

    fp_1s = parse_threshold_session_fp(raw, header_row, col_start=0, name="SessionFP_1s")
    fp_2s = parse_threshold_session_fp(raw, header_row, col_start=9, name="SessionFP_2s")
    fp_3s = parse_threshold_session_fp(raw, header_row, col_start=18, name="SessionFP_3s")

    df = tp_1s.rename(columns={f"Day{i}": f"TP1_Day{i}" for i in range(1, 6)})
    df = df.merge(
        tp_2s.rename(columns={f"Day{i}": f"TP2_Day{i}" for i in range(1, 6)}),
        on="Threshold",
        how="inner"
    )
    df = df.merge(
        tp_3s.rename(columns={f"Day{i}": f"TP3_Day{i}" for i in range(1, 6)}),
        on="Threshold",
        how="inner"
    )
    df = df.merge(
        fp_tbl.rename(columns={f"Day{i}": f"FP_Day{i}" for i in range(1, 6)}),
        on="Threshold",
        how="inner"
    )

    for fp_block in (fp_1s, fp_2s, fp_3s):
        df = df.merge(fp_block, on="Threshold", how="inner")

    # Total false positives recorded during the puff sessions. The sheet stores
    # these per block as a 5-day total only, so they are spread evenly over the
    # five days: the pooled totals still match the sheet's own 'Total FP'
    # column, and the puff-session FPs add no between-day variance.
    df["SessionFP_Total"] = (
            df["SessionFP_1s"] +
            df["SessionFP_2s"] +
            df["SessionFP_3s"]
    )

    for d in range(1, 6):
        df[f"TP_Day{d}"] = (
                df[f"TP1_Day{d}"] +
                df[f"TP2_Day{d}"] +
                df[f"TP3_Day{d}"]
        )

        # Pocket-carry false positives (per day) + puff-session share
        df[f"FP_Day{d}"] = df[f"FP_Day{d}"] + df["SessionFP_Total"] / 5.0

        # Expected: 90 puffs per day per vape
        df[f"FN_Day{d}"] = 90.0 - df[f"TP_Day{d}"]
        df[f"FN_Day{d}"] = df[f"FN_Day{d}"].clip(lower=0)

    return df.sort_values("Threshold").reset_index(drop=True)


# ----------------------------
# LOO Threshold Selection Per Vape
# ----------------------------
def leave_one_day_out_threshold_selection(df_daywise: pd.DataFrame) -> pd.DataFrame:
    thresholds = df_daywise["Threshold"].to_numpy()
    days = [1, 2, 3, 4, 5]

    preferred_threshold = 0.4
    results = []

    for test_day in days:
        train_days = [d for d in days if d != test_day]

        f1_train = []

        for idx, threshold in enumerate(thresholds):
            tp = sum(df_daywise.loc[idx, f"TP_Day{d}"] for d in train_days)
            fp = sum(df_daywise.loc[idx, f"FP_Day{d}"] for d in train_days)
            fn = sum(df_daywise.loc[idx, f"FN_Day{d}"] for d in train_days)

            f1_train.append(round(f1_score(tp, fp, fn), 2))

        f1_train = np.array(f1_train)

        max_f1 = np.max(f1_train)
        candidate_idxs = np.where(f1_train == max_f1)[0]

        preferred_idxs = candidate_idxs[
            np.isclose(thresholds[candidate_idxs], preferred_threshold)
        ]

        if len(preferred_idxs) > 0:
            best_idx = preferred_idxs[0]
        else:
            best_idx = candidate_idxs[np.argmin(thresholds[candidate_idxs])]

        best_threshold = float(thresholds[best_idx])

        tp_test = float(df_daywise.loc[best_idx, f"TP_Day{test_day}"])
        fp_test = float(df_daywise.loc[best_idx, f"FP_Day{test_day}"])
        fn_test = float(df_daywise.loc[best_idx, f"FN_Day{test_day}"])

        precision = precision_score(tp_test, fp_test)
        recall = recall_score(tp_test, fn_test)
        f1 = f1_score(tp_test, fp_test, fn_test)

        results.append({
            "TestDay": test_day,
            "SelectedThreshold": best_threshold,
            "TP_Test": tp_test,
            "FP_Test": fp_test,
            "FN_Test": fn_test,
            "Precision_Test": precision,
            "Recall_Test": recall,
            "F1_Test": f1,
        })

    return pd.DataFrame(results)


# ----------------------------
# Operating threshold shared by the combined analysis
# ----------------------------
def select_modal_threshold(loo_dict: dict) -> float:
    """
    The single operating threshold used for the combined analysis: the value
    selected most often across all leave-one-day-out folds of all vapes.

    Ties are broken by the smallest threshold, matching the tie-break already
    used inside leave_one_day_out_threshold_selection.
    """
    selected = pd.concat(
        [loo_summary["SelectedThreshold"] for loo_summary in loo_dict.values()],
        ignore_index=True,
    ).astype(float)

    counts = selected.value_counts()
    max_count = counts.max()
    tied = sorted(float(t) for t, c in counts.items() if c == max_count)

    return tied[0]


def threshold_row_index(df_daywise: pd.DataFrame, threshold: float) -> int:
    """Row index of `threshold` in a day-wise table, matched with a tolerance."""
    matches = np.where(np.isclose(df_daywise["Threshold"].to_numpy(dtype=float), threshold))[0]

    if len(matches) == 0:
        raise ValueError(f"Threshold {threshold} not present in the day-wise table.")

    return int(matches[0])


# ----------------------------
# Combined 5-Fold Results
# ----------------------------
def compute_combined_results_by_fold(daywise_dict: dict, threshold: float) -> pd.DataFrame:
    """
    Combined per-day counts at one fixed threshold.

    For each held-out day the TP/FP/FN of every vape are read at the same
    threshold and summed, so each of the five rows is a configuration the
    system could actually be deployed in.
    """
    combined_rows = []

    for test_day in range(1, 6):
        tp_total = 0.0
        fp_total = 0.0
        fn_total = 0.0

        for df_daywise in daywise_dict.values():
            idx = threshold_row_index(df_daywise, threshold)

            tp_total += float(df_daywise.loc[idx, f"TP_Day{test_day}"])
            fp_total += float(df_daywise.loc[idx, f"FP_Day{test_day}"])
            fn_total += float(df_daywise.loc[idx, f"FN_Day{test_day}"])

        precision = precision_score(tp_total, fp_total)
        recall = recall_score(tp_total, fn_total)
        f1 = f1_score(tp_total, fp_total, fn_total)

        combined_rows.append({
            "TestDay": test_day,
            "TP_Total": tp_total,
            "FP_Total": fp_total,
            "FN_Total": fn_total,
            "Precision": precision,
            "Recall": recall,
            "F1": f1,
        })

    return pd.DataFrame(combined_rows)


# ----------------------------
# Optional Plot
# ----------------------------
def plot_combined_metrics_by_fold(combined_df: pd.DataFrame, threshold: float):
    days = combined_df["TestDay"].to_numpy()

    plt.figure(figsize=(3.5, 2.6), dpi=200)

    plt.plot(days, combined_df["Precision"], marker="o", label="Precision")
    plt.plot(days, combined_df["Recall"], marker="s", label="Recall")
    plt.plot(days, combined_df["F1"], marker="^", label="F1")

    plt.xticks(days)
    plt.ylim(0, 1.05)
    plt.grid(True, linewidth=0.5, alpha=0.4)

    plt.xlabel("Held-out Day")
    plt.ylabel("Score")
    plt.title(f"Combined Metrics Across 5 Folds (T = {threshold:g} s)")

    plt.legend(frameon=False)
    plt.tight_layout()
    plt.show(block=True)


# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":

    raw = pd.read_excel(DATA_PATH, sheet_name=0, header=None)

    vapes = [
        "Geekbar With Thermistor",
        "NJOY Without Thermistor",
    ]

    set_ieee_style()

    loo_dict = {}
    daywise_dict = {}

    for vape in vapes:
        print("\n==============================")
        print(f"Processing: {vape}")
        print("==============================")

        df_daywise = build_daywise_counts_for_vape(raw, vape)
        loo_summary = leave_one_day_out_threshold_selection(df_daywise)

        loo_dict[vape] = loo_summary
        daywise_dict[vape] = df_daywise

        print("\nLeave-one-day-out summary:")
        print(loo_summary.to_string(index=False))

        print_cluster_ci95(
            prf_with_cluster_ci95(
                loo_summary["TP_Test"],
                loo_summary["FP_Test"],
                loo_summary["FN_Test"],
            ),
            "Per-vape pooled ratio with 95% CI (folds as clusters):",
        )

    # -------------------------------------------------------
    # Combine both vape results by held-out day at ONE threshold:
    # the value selected most often across all folds of all vapes.
    # This gives n = 5 combined fold samples.
    # -------------------------------------------------------
    operating_threshold = select_modal_threshold(loo_dict)

    selected_counts = pd.concat(
        [loo_summary["SelectedThreshold"] for loo_summary in loo_dict.values()],
        ignore_index=True,
    ).value_counts().sort_index()

    print("\n==============================")
    print("COMBINED OPERATING THRESHOLD")
    print("==============================")
    print("Thresholds selected across all folds:")
    for threshold, count in selected_counts.items():
        print(f"  {float(threshold):.1f} s : {count} fold(s)")
    print(f"Most used threshold -> T = {operating_threshold:g} s "
          f"({int(selected_counts.max())}/{int(selected_counts.sum())} folds)")

    combined_df = compute_combined_results_by_fold(daywise_dict, operating_threshold)

    print("\n==============================")
    print(f"COMBINED RESULTS BY FOLD (T = {operating_threshold:g} s)")
    print("==============================")
    print(combined_df.to_string(index=False))

    print_cluster_ci95(
        prf_with_cluster_ci95(
            combined_df["TP_Total"],
            combined_df["FP_Total"],
            combined_df["FN_Total"],
        ),
        f"COMBINED pooled ratio at T = {operating_threshold:g} s "
        f"with 95% CI (folds as clusters):",
    )

    # Optional plot
    plot_combined_metrics_by_fold(combined_df, operating_threshold)
