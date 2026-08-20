# Participant-cluster bootstrap for BOTH pooled and macro Precision/Recall/F1
# -- Human Laboratory Study. Single script for all bootstrap-based CIs.
#
# Mirrors device_bootstrap.py (bench lifecycle testing, "CI Code and
# description/bootstrapcode/"), with participant substituted for device as
# the resampling cluster, n=22, and the same percentile + BCa (bias-corrected
# and accelerated) interval construction. See Bootstrap_Method_Description.docx
# for the full method write-up.
#
# Two different targets are computed, each with its own point estimate and
# its own bootstrap/jackknife loop -- they are NOT the same statistic:
#
#   POOLED -- sum TP/FN/FP across participants FIRST, then take the ratio
#             (e.g. Precision = SumTP / (SumTP+SumFP)). Weights each
#             participant by their own puff count. Same target as
#             Script2's closed-form ratio-of-totals CI_Summary sheet --
#             same point estimate, different (bootstrap) CI method.
#
#   MACRO  -- compute each participant's OWN ratio first (Precision_j =
#             TP_j/(TP_j+FP_j), etc.), then take the plain UNWEIGHTED mean
#             across the 22 participants. Every participant counts equally
#             regardless of puff count.
#
# A puff-weighted average of the 22 participants' own ratios collapses
# algebraically back to the pooled estimate, so there is no way to derive
# one target's CI from the other's bootstrap loop -- each needs its own
# resample-and-recompute procedure, both implemented here.
#
# TP/FN/FP per participant are re-derived from raw Participant Data via
# Script1 (imported unmodified), so this script is self-contained and
# reproducible from source data alone -- not read from any intermediate
# spreadsheet.

import os
import sys
import importlib.util

import numpy as np
import pandas as pd
from scipy import stats

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT1_PATH = os.path.join(THIS_DIR, 'Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py')

_spec = importlib.util.spec_from_file_location('script1_confusion_matrix', SCRIPT1_PATH)
script1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script1)

B, SEED = 10000, 12345  # matches device_bootstrap.py exactly


def get_per_participant_tp_fn_fp(participant_dir):
    sub_folders = sorted([
        name for name in os.listdir(participant_dir)
        if os.path.isdir(os.path.join(participant_dir, name))
    ])
    rows = []
    for participant in sub_folders:
        res = script1.run_participant(participant, os.path.join(participant_dir, participant))
        rows.append((res['participant'], res['TP'], res['FN'], res['FP']))
    return rows


def pooled(M):
    """M: (n, 3) array of [TP, FN, FP] rows. Returns [precision, recall, F1],
    summing across participants before taking the ratio."""
    tp, fn, fp = M.sum(0)
    p, r = tp / (tp + fp), tp / (tp + fn)
    f1 = 2 * p * r / (p + r)
    return np.array([p, r, f1])


def macro(M):
    """M: (n, 3) array of [TP, FN, FP] rows. Returns [precision, recall, F1],
    computing each participant's own ratio first, then averaging unweighted."""
    tp, fn, fp = M[:, 0], M[:, 1], M[:, 2]
    p = tp / (tp + fp)
    r = tp / (tp + fn)
    f1 = 2 * p * r / (p + r)
    return np.array([p.mean(), r.mean(), f1.mean()])


def bca(theta_hat, boot, jack):
    """Bias-corrected and accelerated interval (identical formula to device_bootstrap.py)."""
    z0 = stats.norm.ppf((boot < theta_hat).mean())
    jm = jack.mean()
    a = ((jm - jack) ** 3).sum() / (6 * (((jm - jack) ** 2).sum()) ** 1.5)
    out = []
    for q in (0.025, 0.975):
        z = stats.norm.ppf(q)
        adj = stats.norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))
        out.append(np.percentile(boot, 100 * adj))
    return out


def bootstrap_target(M, target_fn, n, rng):
    """Run the resample-and-recompute bootstrap loop for a given target
    function (pooled or macro). Returns (point_estimate, boot_array, jack_array)."""
    pt = target_fn(M)
    boot = np.array([target_fn(M[rng.integers(0, n, n)]) for _ in range(B)])
    jack = np.array([target_fn(np.delete(M, i, 0)) for i in range(n)])
    return pt, boot, jack


def summarize(pt, boot, jack, labels, target_name):
    rows = []
    print(f"\n{target_name} (n = {len(jack)} participants, B = {B:,}, seed {SEED})")
    print(f"{'metric':10}{'estimate':>10}{'percentile 95% CI':>26}{'BCa 95% CI':>26}")
    for i, lab in enumerate(labels):
        lo, hi = np.percentile(boot[:, i], [2.5, 97.5])
        blo, bhi = bca(pt[i], boot[:, i], jack[:, i])
        print(f"{lab:10}{pt[i]*100:10.2f}"
              f"{f'[{lo*100:.2f}, {hi*100:.2f}]':>26}"
              f"{f'[{blo*100:.2f}, {bhi*100:.2f}]':>26}")
        rows.append({
            'Metric': lab,
            f'{target_name} estimate (%)': round(pt[i] * 100, 4),
            'Percentile 95% CI lower (%)': round(lo * 100, 4),
            'Percentile 95% CI upper (%)': round(hi * 100, 4),
            'BCa 95% CI lower (%)': round(blo * 100, 4),
            'BCa 95% CI upper (%)': round(bhi * 100, 4),
            'Report as (BCa)': f'{pt[i]*100:.1f}% [{blo*100:.1f}%, {bhi*100:.1f}%]',
            'n (clusters = participants)': len(jack),
            'B (bootstrap replicates)': B,
            'seed': SEED,
        })
    return pd.DataFrame(rows)


def main(participant_dir, out_xlsx_path):
    rows = get_per_participant_tp_fn_fp(participant_dir)
    n = len(rows)
    participants = [r[0] for r in rows]
    M = np.array([[tp, fn, fp] for (_, tp, fn, fp) in rows], dtype=float)
    labels = ['Precision', 'Recall', 'F1']

    rng_pooled = np.random.default_rng(SEED)
    pt_pooled, boot_pooled, jack_pooled = bootstrap_target(M, pooled, n, rng_pooled)
    pooled_df = summarize(pt_pooled, boot_pooled, jack_pooled, labels, 'Pooled')

    rng_macro = np.random.default_rng(SEED)
    pt_macro, boot_macro, jack_macro = bootstrap_target(M, macro, n, rng_macro)
    macro_df = summarize(pt_macro, boot_macro, jack_macro, labels, 'Macro')

    tp, fn, fp = M[:, 0], M[:, 1], M[:, 2]
    per_participant_df = pd.DataFrame({
        'Participant': participants,
        'TP': tp.astype(int),
        'FN': fn.astype(int),
        'FP': fp.astype(int),
        'Precision_j': tp / (tp + fp),
        'Recall_j': tp / (tp + fn),
        'F1_j': 2 * (tp / (tp + fp)) * (tp / (tp + fn)) / ((tp / (tp + fp)) + (tp / (tp + fn))),
    })

    method_df = pd.DataFrame({'Note': [
        'Participant-cluster bootstrap for BOTH the POOLED and MACRO Precision/Recall/F1 targets '
        '-- one script, two separate resample-and-recompute loops (they are different statistics '
        'and cannot share a single bootstrap distribution).',
        'POOLED: sum TP/FN/FP across all 22 participants first, then take the ratio '
        '(e.g. Precision = SumTP / (SumTP+SumFP)) -- weights each participant by their own '
        'puff count. Same point estimate as Script2 CI_Summary sheet (closed-form method); '
        'this script gives an alternative bootstrap-based CI for that same target.',
        'MACRO: compute each participant\'s own ratio first (Precision_j = TP_j/(TP_j+FP_j), '
        'etc.), then take the plain unweighted mean across the 22 participants -- every '
        'participant counts equally regardless of puff count.',
        'Percentile 95% CI: resample the 22 participants with replacement, recompute the '
        'target (pooled or macro) on each resample, repeat 10,000 times, take the '
        '2.5th/97.5th percentiles.',
        'BCa 95% CI (the reported method): bias-corrected and accelerated refinement of the '
        'percentile interval, using a leave-one-participant-out jackknife to estimate the '
        'acceleration constant.',
        'Mirrors device_bootstrap.py (bench lifecycle testing) exactly for the pooled target, '
        'with participant substituted for device as the resampling cluster. Same B and seed '
        'as that script, for direct comparability.',
        'TP/FN/FP per participant are re-derived from raw Participant Data via '
        'Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py (imported unmodified) -- not '
        'read from any intermediate spreadsheet.',
        'See Bootstrap_Method_Description.docx (Manuscript/) for the full method write-up.',
    ]})

    with pd.ExcelWriter(out_xlsx_path) as writer:
        per_participant_df.to_excel(writer, sheet_name='Per_Participant_Data', index=False)
        pooled_df.to_excel(writer, sheet_name='Pooled_Bootstrap_Summary', index=False)
        macro_df.to_excel(writer, sheet_name='Macro_Bootstrap_Summary', index=False)
        method_df.to_excel(writer, sheet_name='Method', index=False)

    print(f'\nWritten: {out_xlsx_path}')
    return pooled_df, macro_df


if __name__ == '__main__':
    Participant_Dir = r'C:\Users\claws\Documents\FRIENDS_UB_LAB\FRIENDS Paper Lab Data, Code and Results\Participant Data'
    Out_Xlsx = r'C:\Users\claws\Documents\FRIENDS_UB_LAB\FRIENDS Paper Lab Data, Code and Results\Results\Human_Study_Cluster_Bootstrap_CI.xlsx'
    if len(sys.argv) >= 3:
        Participant_Dir = sys.argv[1]
        Out_Xlsx = sys.argv[2]
    main(Participant_Dir, Out_Xlsx)
