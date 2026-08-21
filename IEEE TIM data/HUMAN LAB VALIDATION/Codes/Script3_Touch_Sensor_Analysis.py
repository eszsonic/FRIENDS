# Touch-sensor gating analysis, reconciled onto Script1's verified pipeline.
#
# Background: Script2_Puff_Touch_Analysis.py independently re-implements
# device-signal parsing/binarization to test how detection changes when
# FRIENDS puffs are required to temporally overlap a touch-sensor
# activation. That re-implementation does not reproduce Script1's already
# -verified 888-puff total (it gives 919 raw / 829 post-binarization,
# unevenly across participants -- see FRIENDS2094: 48 vs 28). Since Script1
# is the validated source of truth for puff counting (866 camera / 888
# FRIENDS / 799 TP / 67 FN / 73 FP, reproduced byte-for-byte from raw data),
# this script performs the SAME touch-gating question -- "of the FRIENDS
# puffs that make up the reconciled confusion matrix, how many temporally
# overlap a touch event, and what happens to precision/recall/F1 if
# detection is restricted to those?" -- using Script1's own functions
# unmodified, so the touch-gated numbers are directly comparable to the
# already-verified 888/799/67/73 baseline.
#
# Method:
#   1. Run Script1's exact pipeline (imported, not reimplemented) to get,
#      per participant: friends_puffs (aligned frame-index tuples),
#      friends_target (camera-puff index each FRIENDS puff matched, or
#      None), camera_puffs, best_lag, session_start_sec.
#   2. Touch and puff events share the FRIENDS device's own clock, so
#      touch-overlap is decided in raw DEVICE-clock seconds, not in the
#      camera-aligned frame grid (the camera alignment lag exists only to
#      match device events to video events, and must not be applied to a
#      device-internal puff-vs-touch comparison). Each aligned FRIENDS puff
#      is converted back to device-clock seconds by inverting Script1's
#      alignment shift (original_frame = aligned_frame + best_lag), then
#      compared against raw TOUCH intervals parsed from the same device
#      file with the same session-start anchor Script1 uses.
#   3. Touch-gated TP'/FN'/FP' use the same reconciled definition as
#      Script1 (TP' = unique true puffs matched by >=1 touch-overlapping
#      FRIENDS puff), restricted to the subset of FRIENDS puffs that
#      overlap a touch event.

import os
import sys
import re
import importlib.util
from datetime import datetime

import numpy as np
import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT1_PATH = os.path.join(THIS_DIR, 'Script1_0.4sec_threshold_performance_metrics.py')

_spec = importlib.util.spec_from_file_location('script1_confusion_matrix', SCRIPT1_PATH)
script1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script1)

FRAME_RATE = script1.FRAME_RATE
TOLERANCE_SEC = script1.TOLERANCE_SEC
MIN_PUFF_DURATION = script1.MIN_PUFF_DURATION

# Mirrors Script1.parse_device_event_log's regex verbatim (identical pattern)
# but returns ALL events (PUFF and TOUCH), because Script1's own function
# discards TOUCH rows before returning.
_DEVICE_LINE_RE = re.compile(
    r'\s*(PUFF|TOUCH)\s+(\d{4}-\d{2}-\d{2}) '
    r'(\d{2}:\d{2}:\d{2}\.\d+)-(\d{2}:\d{2}:\d{2}\.\d+)\s+(\d+\.\d+)')


def parse_all_device_events(file_path):
    data = []
    with open(file_path, 'r') as file:
        for line in file:
            m = _DEVICE_LINE_RE.match(line)
            if m:
                event, date_part, start_time, end_time, duration = m.groups()
                start_time = datetime.strptime(start_time, "%H:%M:%S.%f").time()
                end_time = datetime.strptime(end_time, "%H:%M:%S.%f").time()
                duration_sec = float(duration) / 1000
                data.append([event, start_time, end_time, duration_sec])
    df = pd.DataFrame(data, columns=["Event", "Start Time", "End Time", "Duration (s)"])
    all_starts = df["Start Time"].apply(
        lambda t: t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6)
    session_start_sec = float(all_starts.min())
    return df, session_start_sec


def _t2s(t):
    return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6


def run_participant_touch(participant, participant_dir_path):
    video_dir_path = os.path.join(participant_dir_path, 'VIDEO_DATA')
    video_input_file, video_ext = script1.find_video_file(video_dir_path)
    device_dir_path = os.path.join(participant_dir_path, 'DEVICE_DATA')
    device_files = [f for f in os.listdir(device_dir_path) if f.endswith('.txt')]
    device_input_file = os.path.join(device_dir_path, device_files[0])

    # ---- video side: identical to Script1 ----
    video_cleaned_df = script1.parse_video_event_log(video_input_file, video_ext)
    (_, camera_binary, _, obstruction_binary, n_cam_frames) = script1.process_video_events(video_cleaned_df)

    # ---- device side: all events (so we get TOUCH rows too), same anchor as Script1 ----
    all_events_df, session_start_sec = parse_all_device_events(device_input_file)
    puff_events_df = all_events_df[all_events_df['Event'] == 'PUFF'].copy()
    touch_events_df = all_events_df[all_events_df['Event'] == 'TOUCH'].copy()
    filtered_puff_events_df = puff_events_df[puff_events_df['Duration (s)'] > MIN_PUFF_DURATION]

    device_binary, n_dev_frames = script1.generate_device_binary_array(filtered_puff_events_df, session_start_sec)

    camera_signal, friends_signal, obstruction_mask = script1.build_unified_frame_arrays(
        camera_binary, obstruction_binary, device_binary, n_cam_frames, n_dev_frames)

    fs = FRAME_RATE
    N = len(camera_signal)

    xcorr_vals = script1.fft_correlate_full(friends_signal, camera_signal)
    lags = np.arange(-len(camera_signal) + 1, len(friends_signal))
    best_lag = lags[np.argmax(xcorr_vals)]

    # identical shift block to Script1.run_participant
    aligned_friends_signal = np.zeros_like(friends_signal)
    if best_lag > 0:
        aligned_friends_signal[:N - best_lag] = friends_signal[best_lag:]
    elif best_lag < 0:
        aligned_friends_signal[-best_lag:] = friends_signal[:N + best_lag]
    else:
        aligned_friends_signal = friends_signal.copy()

    camera_puffs, friends_puffs, camera_matched, friends_target = script1.match_puffs(
        camera_signal, aligned_friends_signal, fs,
        obstruction_mask=obstruction_mask, tolerance_sec=TOLERANCE_SEC)

    true_n = len(camera_puffs)
    tp = sum(camera_matched)
    fn = true_n - tp
    fp = sum(1 for t in friends_target if t is None)
    assert tp + fn == true_n

    # ---- touch overlap, decided on the device's own clock (no lag applied) ----
    touch_intervals_sec = [
        (_t2s(row['Start Time']), _t2s(row['End Time']))
        for _, row in touch_events_df.iterrows()
    ]

    def _overlaps_touch(dev_start_sec, dev_end_sec):
        return any(dev_start_sec < te and ts < dev_end_sec for ts, te in touch_intervals_sec)

    touch_overlap_flags = []
    for (start_frame, end_frame) in friends_puffs:
        orig_start_frame = start_frame + best_lag
        orig_end_frame = end_frame + best_lag
        dev_start_sec = session_start_sec + orig_start_frame / fs
        dev_end_sec = session_start_sec + orig_end_frame / fs
        touch_overlap_flags.append(_overlaps_touch(dev_start_sec, dev_end_sec))

    n_touch_overlap = sum(touch_overlap_flags)

    # ---- touch-gated confusion matrix, same reconciled definition as Script1 ----
    touch_gated_matched_camera_idx = set()
    fp_touch = 0
    for j, overlaps in enumerate(touch_overlap_flags):
        if not overlaps:
            continue
        if friends_target[j] is not None:
            touch_gated_matched_camera_idx.add(friends_target[j])
        else:
            fp_touch += 1
    tp_touch = len(touch_gated_matched_camera_idx)
    fn_touch = true_n - tp_touch

    def _prf(tp_, fn_, fp_):
        p = tp_ / (tp_ + fp_) if (tp_ + fp_) > 0 else np.nan
        r = tp_ / (tp_ + fn_) if (tp_ + fn_) > 0 else np.nan
        f1 = 2 * p * r / (p + r) if p and r and not np.isnan(p) and not np.isnan(r) and (p + r) > 0 else np.nan
        return p, r, f1

    precision, recall, f1 = _prf(tp, fn, fp)
    precision_touch, recall_touch, f1_touch = _prf(tp_touch, fn_touch, fp_touch)

    return {
        'participant': participant,
        'true_puffs': true_n,
        'friends_puffs_all': len(friends_puffs),
        'TP': tp, 'FN': fn, 'FP': fp,
        'precision': precision, 'recall': recall, 'f1': f1,
        'friends_puffs_touch_overlap': n_touch_overlap,
        'TP_touch': tp_touch, 'FN_touch': fn_touch, 'FP_touch': fp_touch,
        'precision_touch': precision_touch, 'recall_touch': recall_touch, 'f1_touch': f1_touch,
    }


def main(participant_dir, out_xlsx_path):
    sub_folders = sorted([
        name for name in os.listdir(participant_dir)
        if os.path.isdir(os.path.join(participant_dir, name))
    ])

    rows = []
    for participant in sub_folders:
        print(f'Processing {participant} ...')
        res = run_participant_touch(participant, os.path.join(participant_dir, participant))
        rows.append(res)

    df = pd.DataFrame(rows)

    TP, FN, FP = int(df['TP'].sum()), int(df['FN'].sum()), int(df['FP'].sum())
    true_total = int(df['true_puffs'].sum())
    friends_total = int(df['friends_puffs_all'].sum())
    assert TP + FN == true_total
    p_pool = TP / (TP + FP)
    r_pool = TP / (TP + FN)
    f1_pool = 2 * p_pool * r_pool / (p_pool + r_pool)

    TPt, FNt, FPt = int(df['TP_touch'].sum()), int(df['FN_touch'].sum()), int(df['FP_touch'].sum())
    touch_total = int(df['friends_puffs_touch_overlap'].sum())
    p_pool_t = TPt / (TPt + FPt) if (TPt + FPt) > 0 else float('nan')
    r_pool_t = TPt / (TPt + FNt) if (TPt + FNt) > 0 else float('nan')
    f1_pool_t = (2 * p_pool_t * r_pool_t / (p_pool_t + r_pool_t)
                 if p_pool_t and r_pool_t and (p_pool_t + r_pool_t) > 0 else float('nan'))

    with pd.ExcelWriter(out_xlsx_path) as writer:
        df.to_excel(writer, sheet_name='Per_Participant', index=False)
        pd.DataFrame([{
            'Total Camera Puff Count': true_total,
            'Total FRIENDS Puff Count': friends_total,
            'TP': TP, 'FN': FN, 'FP': FP,
            'Pooled Precision': round(p_pool, 4), 'Pooled Recall': round(r_pool, 4), 'Pooled F1': round(f1_pool, 4),
            'FRIENDS puffs with touch overlap': touch_total,
            'Touch overlap % of FRIENDS puffs': round(100 * touch_total / friends_total, 1),
            'TP (touch-gated)': TPt, 'FN (touch-gated)': FNt, 'FP (touch-gated)': FPt,
            'Pooled Precision (touch-gated)': round(p_pool_t, 4),
            'Pooled Recall (touch-gated)': round(r_pool_t, 4),
            'Pooled F1 (touch-gated)': round(f1_pool_t, 4),
            'Mean Precision (touch-gated, unweighted)': round(df['precision_touch'].mean(), 4),
            'Mean Recall (touch-gated, unweighted)': round(df['recall_touch'].mean(), 4),
            'Mean F1 (touch-gated, unweighted)': round(df['f1_touch'].mean(), 4),
        }]).to_excel(writer, sheet_name='Pooled_Summary', index=False)

    print('\n=== DONE ===')
    print(f'Baseline (matches Script1): Total Camera={true_total}  Total FRIENDS={friends_total}  '
          f'TP={TP} FN={FN} FP={FP}  P={p_pool:.4f} R={r_pool:.4f} F1={f1_pool:.4f}')
    print(f'\nTouch-gated: FRIENDS puffs with touch overlap = {touch_total} / {friends_total} '
          f'({100*touch_total/friends_total:.1f}%)')
    print(f'Touch-gated pooled: TP={TPt} FN={FNt} FP={FPt}  '
          f'P={p_pool_t:.4f} R={r_pool_t:.4f} F1={f1_pool_t:.4f}')
    print(f"Touch-gated mean (unweighted): P={df['precision_touch'].mean():.4f} "
          f"R={df['recall_touch'].mean():.4f} F1={df['f1_touch'].mean():.4f}")
    print(f'\nWritten: {out_xlsx_path}')
    return df


if __name__ == '__main__':
    # Relative to this script's own location, so the defaults work
    # regardless of who clones the repo or where it's placed on disk.
    Participant_Dir = os.path.join(THIS_DIR, '..', 'Participant Data')
    Out_Xlsx = os.path.join(THIS_DIR, '..', 'Results', 'Touch_Sensor_Analysis.xlsx')
    if len(sys.argv) >= 3:
        Participant_Dir = sys.argv[1]
        Out_Xlsx = sys.argv[2]
    main(Participant_Dir, Out_Xlsx)
