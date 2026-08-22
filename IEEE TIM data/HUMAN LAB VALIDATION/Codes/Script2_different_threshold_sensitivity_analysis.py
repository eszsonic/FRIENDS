# Detection-threshold sensitivity analysis -- addresses Comment 1.7
# ("provide a clearer rationale for this threshold, including sensitivity
# analysis and its effect on precision, recall, and missed short puffs in
# the human validation dataset").
#
# Pooled precision/recall/F1 at detection thresholds of 0, 0.2, 0.4, and
# 0.6 s, each with a 95% BCa bootstrap CI -- the identical participant-
# cluster bootstrap method (percentile + BCa, B=10,000, seed=12345) used
# for the pooled CI at the 0.4 s production threshold elsewhere in this
# pipeline, applied here at every threshold in the sweep so the numbers
# match exactly at 0.4 s.
#
# Reuses Script1's own functions unmodified (parsing, alignment, matching)
# -- the same verified pipeline that produces the manuscript's
# 866/888/799/67/73 confusion matrix, just re-run once per threshold. No
# intermediate spreadsheet is read; reproducible from raw Participant Data
# alone.

import os
import sys
import importlib.util

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT1_PATH = os.path.join(THIS_DIR, 'Script1_0.4sec_threshold_performance_metrics.py')

_spec = importlib.util.spec_from_file_location('script1_confusion_matrix', SCRIPT1_PATH)
script1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script1)

THRESHOLD_SWEEP = [0.0, 0.2, 0.4, 0.6]
B, SEED = 10000, 12345  # matches the bench-testing coauthor's device_bootstrap.py exactly


def _pooled_prf(M):
    """M: (n, 3) array of [TP, FN, FP] rows, one per participant. Returns
    [precision, recall, F1], summing across participants before the ratio
    -- the pooled definition."""
    tp, fn, fp = M.sum(0)
    p = tp / (tp + fp) if (tp + fp) > 0 else np.nan
    r = tp / (tp + fn) if (tp + fn) > 0 else np.nan
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else np.nan
    return np.array([p, r, f1])


def _bca(theta_hat, boot, jack):
    """Bias-corrected and accelerated interval -- identical formula to
    device_bootstrap.py (bench lifecycle testing)."""
    z0 = stats.norm.ppf((boot < theta_hat).mean())
    jm = jack.mean()
    a = ((jm - jack) ** 3).sum() / (6 * (((jm - jack) ** 2).sum()) ** 1.5)
    out = []
    for q in (0.025, 0.975):
        z = stats.norm.ppf(q)
        adj = stats.norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))
        out.append(np.percentile(boot, 100 * adj))
    return out


def threshold_sensitivity(participant_dir, out_dir):
    sub_folders = sorted([
        name for name in os.listdir(participant_dir)
        if os.path.isdir(os.path.join(participant_dir, name))
    ])
    n = len(sub_folders)
    labels = ['Precision', 'Recall', 'F1']

    print(f"\n=== Threshold sensitivity ({THRESHOLD_SWEEP} s), with BCa 95% CI "
          f"(participant-cluster bootstrap, B={B:,}, seed={SEED}) ===")
    rows = []
    for thr in THRESHOLD_SWEEP:
        script1.MIN_PUFF_DURATION = thr
        M = []
        for participant in sub_folders:
            res = script1.run_participant(participant, os.path.join(participant_dir, participant))
            M.append([res['TP'], res['FN'], res['FP']])
        M = np.array(M, dtype=float)
        TP, FN, FP = M.sum(0)
        precision, recall, f1 = script1.precision_recall_f1(TP, FN, FP)

        pt = _pooled_prf(M)
        rng = np.random.default_rng(SEED)
        boot = np.array([_pooled_prf(M[rng.integers(0, n, n)]) for _ in range(B)])
        jack = np.array([_pooled_prf(np.delete(M, i, 0)) for i in range(n)])

        row = {'Threshold (s)': thr, 'TP': int(TP), 'FN': int(FN), 'FP': int(FP)}
        ci_print = []
        for i, lab in enumerate(labels):
            blo, bhi = _bca(pt[i], boot[:, i], jack[:, i])
            row[lab] = round(pt[i], 4)
            row[f'{lab} 95% CI lower (BCa)'] = round(blo, 4)
            row[f'{lab} 95% CI upper (BCa)'] = round(bhi, 4)
            ci_print.append(f"{lab}={pt[i]:.4f} [{blo:.4f}, {bhi:.4f}]")
        rows.append(row)
        print(f"  threshold={thr:.1f}s  TP={int(TP)} FN={int(FN)} FP={int(FP)}   " + '  '.join(ci_print))

    threshold_df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    colors = {'Precision': '#4C72B0', 'Recall': '#DD8452', 'F1': '#55A868'}
    markers = {'Precision': 'o', 'Recall': 's', 'F1': '^'}
    x = threshold_df['Threshold (s)'].values
    for lab in labels:
        y = threshold_df[lab].values
        lo = y - threshold_df[f'{lab} 95% CI lower (BCa)'].values
        hi = threshold_df[f'{lab} 95% CI upper (BCa)'].values - y
        ax.errorbar(x, y, yerr=[lo, hi], fmt=markers[lab] + '-', label=lab,
                    color=colors[lab], capsize=4, linewidth=1.5, markersize=7)
    ax.set_xlabel('Detection threshold (s)', fontsize=11)
    ax.set_ylabel('Score', fontsize=11)
    ax.set_title('Pooled Precision / Recall / F1 vs. Detection Threshold\n'
                 '(Human Laboratory Study; error bars = 95% BCa bootstrap CI)', fontsize=12)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=9)
    ax.grid(True, linestyle=':', alpha=0.4)
    plt.tight_layout()
    fig_path = os.path.join(out_dir, 'Threshold_Sensitivity_PRF1.png')
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {fig_path}')

    return threshold_df


def main(participant_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)

    # threshold_sensitivity() sweeps script1.MIN_PUFF_DURATION through
    # THRESHOLD_SWEEP and leaves it at the final value (0.6 s) -- restore
    # whatever it was before this call, so a later import-and-reuse of this
    # script1 instance (e.g. script1.run_participant() called again after
    # main() returns) doesn't silently run at the wrong threshold.
    original_threshold = script1.MIN_PUFF_DURATION
    try:
        threshold_df = threshold_sensitivity(participant_dir, out_dir)
    finally:
        script1.MIN_PUFF_DURATION = original_threshold

    out_xlsx = os.path.join(out_dir, 'Threshold_Sensitivity_Performance_Metrics.xlsx')
    with pd.ExcelWriter(out_xlsx) as writer:
        threshold_df.to_excel(writer, sheet_name='Threshold_Sensitivity', index=False)
        pd.DataFrame({'Note': [
            'Script1_0.4sec_threshold_performance_metrics.py re-run once per threshold in '
            f'{THRESHOLD_SWEEP}, pooling TP/FN/FP across all 22 participants at each threshold, '
            'unmodified otherwise. 0.0 s effectively applies no filter (Script1 keeps puffs with '
            'duration > threshold).',
            'Each threshold\'s Precision/Recall/F1 has a 95% BCa (bias-corrected and accelerated) '
            'bootstrap CI: resample the 22 participants with replacement, sum their TP/FN/FP, '
            f'recompute the pooled ratio, across {B:,} replicates (seed={SEED}), with a '
            'leave-one-participant-out jackknife correction for bias and skew -- the identical '
            'method used for the pooled CI at the 0.4 s production threshold elsewhere in this '
            'pipeline, and matching the bench-testing coauthor\'s device_bootstrap.py.',
            'Reuses Script1_0.4sec_threshold_performance_metrics.py (imported unmodified) -- not '
            'read from any intermediate spreadsheet.',
        ]}).to_excel(writer, sheet_name='Method', index=False)

    print(f'\nWritten: {out_xlsx}')
    return threshold_df


if __name__ == '__main__':
    # Relative to this script's own location, so the defaults work
    # regardless of who clones the repo or where it's placed on disk.
    Participant_Dir = os.path.join(THIS_DIR, '..', 'Participant Data')
    Out_Dir = os.path.join(THIS_DIR, '..', 'Results', 'Threshold_Sensitivity_Performance_Metrics')
    if len(sys.argv) >= 3:
        Participant_Dir = sys.argv[1]
        Out_Dir = sys.argv[2]
    main(Participant_Dir, Out_Dir)
