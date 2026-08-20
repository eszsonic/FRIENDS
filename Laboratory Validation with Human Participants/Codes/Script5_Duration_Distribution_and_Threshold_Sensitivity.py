# Puff-duration distribution (camera vs. FRIENDS) + detection-threshold
# sensitivity analysis -- addresses Comment 1.7 ("provide a clearer
# rationale for this threshold, including sensitivity analysis and its
# effect on precision, recall, and missed short puffs in the human
# validation dataset"), per the professor's specific request:
#
#   Part A: duration of every individual camera puff and every individual
#           FRIENDS puff (not participant averages) -- mean, SD, range,
#           95% CI, and a histogram for each.
#   Part B: pooled precision/recall/F1 at detection thresholds of
#           0, 0.2, 0.4, and 0.6 s.
#
# Reuses Script1's own functions unmodified for both parts (parsing,
# alignment, matching) -- this is the same verified pipeline that produces
# the manuscript's 866/888/799/67/73 confusion matrix, just re-run at
# different thresholds (Part B) and with the individual puff durations
# exposed rather than only participant-level summaries (Part A). No
# intermediate spreadsheet is read; both parts are reproducible from raw
# Participant Data alone.

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
SCRIPT1_PATH = os.path.join(THIS_DIR, 'Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py')

_spec = importlib.util.spec_from_file_location('script1_confusion_matrix', SCRIPT1_PATH)
script1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script1)

PRODUCTION_THRESHOLD = 0.4  # the threshold used everywhere else in the manuscript
THRESHOLD_SWEEP = [0.0, 0.2, 0.4, 0.6]


# ---------------------------------------------------------------
# Part A: every individual puff duration (camera and FRIENDS), at the
# production (0.4 s) threshold -- mirrors Script1.run_participant's
# internals up through match_puffs, but returns the raw (start, end)
# frame tuples instead of only a per-participant summary, so every
# individual puff's duration is available, not just the participant mean.
# ---------------------------------------------------------------

def get_all_puff_durations(participant, participant_dir_path, min_puff_duration):
    script1.MIN_PUFF_DURATION = min_puff_duration

    video_dir_path = os.path.join(participant_dir_path, 'VIDEO_DATA')
    video_input_file, video_ext = script1.find_video_file(video_dir_path)
    device_dir_path = os.path.join(participant_dir_path, 'DEVICE_DATA')
    device_files = [f for f in os.listdir(device_dir_path) if f.endswith('.txt')]
    device_input_file = os.path.join(device_dir_path, device_files[0])

    video_cleaned_df = script1.parse_video_event_log(video_input_file, video_ext)
    (_, camera_binary, _, obstruction_binary, n_cam_frames) = script1.process_video_events(video_cleaned_df)

    device_events_df, session_start_sec = script1.parse_device_event_log(device_input_file)
    filtered_device_events_df = device_events_df[device_events_df['Duration (s)'] > min_puff_duration]
    device_binary, n_dev_frames = script1.generate_device_binary_array(filtered_device_events_df, session_start_sec)

    camera_signal, friends_signal, obstruction_mask = script1.build_unified_frame_arrays(
        camera_binary, obstruction_binary, device_binary, n_cam_frames, n_dev_frames)

    fs = script1.FRAME_RATE
    N = len(camera_signal)
    xcorr_vals = script1.fft_correlate_full(friends_signal, camera_signal)
    lags = np.arange(-len(camera_signal) + 1, len(friends_signal))
    best_lag = lags[np.argmax(xcorr_vals)]

    aligned_friends_signal = np.zeros_like(friends_signal)
    if best_lag > 0:
        aligned_friends_signal[:N - best_lag] = friends_signal[best_lag:]
    elif best_lag < 0:
        aligned_friends_signal[-best_lag:] = friends_signal[:N + best_lag]
    else:
        aligned_friends_signal = friends_signal.copy()

    camera_puffs, friends_puffs, _, _ = script1.match_puffs(
        camera_signal, aligned_friends_signal, fs,
        obstruction_mask=obstruction_mask, tolerance_sec=script1.TOLERANCE_SEC)

    cam_durs = [(ce - cs) / fs for cs, ce in camera_puffs]
    fri_durs = [(fe - fs_) / fs for fs_, fe in friends_puffs]
    return cam_durs, fri_durs


def part_a_duration_distribution(participant_dir, out_dir):
    sub_folders = sorted([
        name for name in os.listdir(participant_dir)
        if os.path.isdir(os.path.join(participant_dir, name))
    ])

    all_cam_durs, all_fri_durs = [], []
    for participant in sub_folders:
        cam_durs, fri_durs = get_all_puff_durations(
            participant, os.path.join(participant_dir, participant), PRODUCTION_THRESHOLD)
        all_cam_durs.extend(cam_durs)
        all_fri_durs.extend(fri_durs)

    def describe(durs, label):
        arr = np.asarray(durs, dtype=float)
        n = len(arr)
        mean = arr.mean()
        sd = arr.std(ddof=1)
        se = sd / np.sqrt(n)
        t_crit = stats.t.ppf(0.975, n - 1)
        ci_lo, ci_hi = mean - t_crit * se, mean + t_crit * se
        stats_row = {
            'Series': label, 'n': n, 'Mean (s)': round(mean, 4), 'SD (s)': round(sd, 4),
            'Min (s)': round(arr.min(), 4), 'Max (s)': round(arr.max(), 4),
            '95% CI lower (s)': round(ci_lo, 4), '95% CI upper (s)': round(ci_hi, 4),
        }
        print(f"{label}: n={n}  mean={mean:.4f}  SD={sd:.4f}  range=[{arr.min():.4f}, {arr.max():.4f}]  "
              f"95% CI=[{ci_lo:.4f}, {ci_hi:.4f}]")
        return stats_row, arr

    print(f"\n=== Part A: individual puff duration distribution (threshold = {PRODUCTION_THRESHOLD} s) ===")
    cam_row, cam_arr = describe(all_cam_durs, 'Camera (video-coded)')
    fri_row, fri_arr = describe(all_fri_durs, 'FRIENDS')
    summary_df = pd.DataFrame([cam_row, fri_row])

    # Histograms, matching the style described for the camera-duration figure:
    # a dashed line at the 0.4 s device-side filter threshold.
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(cam_arr, bins=40, color='steelblue', edgecolor='white', alpha=0.85)
    ax.axvline(PRODUCTION_THRESHOLD, color='crimson', linestyle='--', linewidth=1.5,
               label=f'{PRODUCTION_THRESHOLD} s device-side filter threshold')
    ax.set_xlabel('Camera (video-coded) puff duration (s)', fontsize=11)
    ax.set_ylabel('Count', fontsize=11)
    ax.set_title(f'Distribution of {len(cam_arr)} Video-Coded Camera Puff Durations\n(all 22 participants)',
                 fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, linestyle=':', alpha=0.4)
    plt.tight_layout()
    cam_fig_path = os.path.join(out_dir, 'Histogram_Camera_Puff_Duration.png')
    plt.savefig(cam_fig_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {cam_fig_path}')

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(fri_arr, bins=40, color='darkorange', edgecolor='white', alpha=0.85)
    ax.axvline(PRODUCTION_THRESHOLD, color='crimson', linestyle='--', linewidth=1.5,
               label=f'{PRODUCTION_THRESHOLD} s device-side filter threshold')
    ax.set_xlabel('FRIENDS puff duration (s)', fontsize=11)
    ax.set_ylabel('Count', fontsize=11)
    ax.set_title(f'Distribution of {len(fri_arr)} FRIENDS-Detected Puff Durations\n(all 22 participants, '
                 f'{PRODUCTION_THRESHOLD} s threshold applied)', fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, linestyle=':', alpha=0.4)
    plt.tight_layout()
    fri_fig_path = os.path.join(out_dir, 'Histogram_FRIENDS_Puff_Duration.png')
    plt.savefig(fri_fig_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {fri_fig_path}')

    per_puff_df = pd.DataFrame({
        'Camera puff duration (s)': pd.Series(all_cam_durs),
        'FRIENDS puff duration (s)': pd.Series(all_fri_durs),
    })
    return summary_df, per_puff_df


# ---------------------------------------------------------------
# Part B: pooled precision/recall/F1 at each detection threshold.
# Reuses Script1.run_participant() directly (its own TP/FN/FP), just with
# MIN_PUFF_DURATION swept across the requested thresholds.
# ---------------------------------------------------------------

def part_b_threshold_sensitivity(participant_dir, out_dir):
    sub_folders = sorted([
        name for name in os.listdir(participant_dir)
        if os.path.isdir(os.path.join(participant_dir, name))
    ])

    print(f"\n=== Part B: threshold sensitivity ({THRESHOLD_SWEEP} s) ===")
    rows = []
    for thr in THRESHOLD_SWEEP:
        script1.MIN_PUFF_DURATION = thr
        TP = FN = FP = 0
        for participant in sub_folders:
            res = script1.run_participant(participant, os.path.join(participant_dir, participant))
            TP += res['TP']
            FN += res['FN']
            FP += res['FP']
        precision, recall, f1 = script1.precision_recall_f1(TP, FN, FP)
        rows.append({
            'Threshold (s)': thr, 'TP': TP, 'FN': FN, 'FP': FP,
            'Precision': round(precision, 4), 'Recall': round(recall, 4), 'F1': round(f1, 4),
        })
        print(f"  threshold={thr:.1f}s  TP={TP} FN={FN} FP={FP}  "
              f"P={precision:.4f} R={recall:.4f} F1={f1:.4f}")

    threshold_df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(threshold_df['Threshold (s)'], threshold_df['Precision'], 'o-', label='Precision', color='#4C72B0')
    ax.plot(threshold_df['Threshold (s)'], threshold_df['Recall'], 's-', label='Recall', color='#DD8452')
    ax.plot(threshold_df['Threshold (s)'], threshold_df['F1'], '^-', label='F1', color='#55A868')
    ax.set_xlabel('Detection threshold (s)', fontsize=11)
    ax.set_ylabel('Score', fontsize=11)
    ax.set_title('Pooled Precision / Recall / F1 vs. Detection Threshold\n(Human Laboratory Study)', fontsize=12)
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

    summary_df, per_puff_df = part_a_duration_distribution(participant_dir, out_dir)
    threshold_df = part_b_threshold_sensitivity(participant_dir, out_dir)

    # restore production threshold as the module state, in case this script
    # is imported and reused elsewhere in the same process
    script1.MIN_PUFF_DURATION = PRODUCTION_THRESHOLD

    out_xlsx = os.path.join(out_dir, 'Duration_Distribution_and_Threshold_Sensitivity.xlsx')
    with pd.ExcelWriter(out_xlsx) as writer:
        summary_df.to_excel(writer, sheet_name='Duration_Summary', index=False)
        per_puff_df.to_excel(writer, sheet_name='Per_Puff_Durations', index=False)
        threshold_df.to_excel(writer, sheet_name='Threshold_Sensitivity', index=False)
        pd.DataFrame({'Note': [
            'Part A (Duration_Summary, Per_Puff_Durations): every individual camera puff duration (866, '
            'video-coded ground truth, no threshold applied) and every individual FRIENDS puff duration '
            f'({PRODUCTION_THRESHOLD} s production threshold applied, matching every other result in the '
            'manuscript) -- not participant averages. Mean/SD/range/95% CI (t-interval) computed directly '
            'from these pooled individual-puff values.',
            'Part B (Threshold_Sensitivity): Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py re-run once '
            f'per threshold in {THRESHOLD_SWEEP}, pooling TP/FN/FP across all 22 participants at each '
            'threshold, unmodified otherwise. 0.0 s effectively applies no filter (Script1 keeps puffs with '
            'duration > threshold).',
            'Both parts reuse Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py (imported unmodified) -- '
            'not read from any intermediate spreadsheet.',
        ]}).to_excel(writer, sheet_name='Method', index=False)

    print(f'\nWritten: {out_xlsx}')
    return summary_df, per_puff_df, threshold_df


if __name__ == '__main__':
    Participant_Dir = r'C:\Users\claws\Documents\FRIENDS\Laboratory Validation with Human Participants\Participant Data'
    Out_Dir = r'C:\Users\claws\Documents\FRIENDS\Laboratory Validation with Human Participants\Duration_Distribution_and_Threshold_Sensitivity'
    if len(sys.argv) >= 3:
        Participant_Dir = sys.argv[1]
        Out_Dir = sys.argv[2]
    main(Participant_Dir, Out_Dir)
