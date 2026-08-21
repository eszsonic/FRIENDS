# Puff Detection Confusion Matrix -- Reconciled TP/FN/FP Definition
#
# Background: ES (professor) flagged that the manuscript's reported
# 815 TP + 67 FN = 882, which does not equal the 866 true (video-coded)
# puffs. Root cause: the original pipeline's "hits" counter is incremented
# once per FRIENDS device puff that overlaps a true puff, so when the
# device signal drops out mid-puff and one true puff is logged as 2-3
# separate device detections, each fragment was counted as its own hit
# (815 = 799 unique true puffs detected + 16 "extra" fragment hits from
# 14 over-segmented true puffs).
#
# This script fixes the definition so the confusion matrix is internally
# consistent by construction:
#
#     TP  = number of UNIQUE true (video) puffs matched by >=1 FRIENDS puff
#     FN  = number of true puffs matched by zero FRIENDS puffs
#           => TP + FN == total true puffs, ALWAYS (assertion enforced below)
#     FP  = number of FRIENDS puffs that matched zero true puffs
#           (unchanged from the original definition -- this was already
#           correct, since it's counted on the device side only)
#
# Puff fragmentation (a true puff detected as >1 separate FRIENDS puffs)
# is reported separately as a diagnostic, not folded into TP or FP.
#
# Threshold used: 0.4 s minimum FRIENDS puff duration (the manuscript's
# production setting). Uses the same validated video/device parsing,
# integer-frame alignment, and FFT-based cross-correlation as
# Thermistor_Data_Puff_Analysis_v2.py / Puff_Duration_Threshold_Sensitivity_Analysis.py.

import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta
import os
import sys
from collections import Counter
from scipy import stats

FRAME_RATE = 25
TOLERANCE_SEC = 0.5
MIN_PUFF_DURATION = 0.4   # manuscript's production threshold
B, SEED = 10000, 12345    # bootstrap replicates / seed -- matches the bench-testing
                           # coauthor's device_bootstrap.py, and every other bootstrap
                           # CI computed elsewhere in this pipeline


# ---------------------------------------------------------------
# Video parsing
# ---------------------------------------------------------------

_VIDEO_REQUIRED_COLS = [
    'Time_Relative_hmsf', 'Time_Relative_sf',
    'Time_Absolute_hms', 'Time_Absolute_f',
    'Duration_sf', 'Behavior', 'Event_Type'
]


def find_video_file(video_dir_path):
    for ext in ('txt', 'xlsx', 'xls'):
        matches = [f for f in os.listdir(video_dir_path) if f.lower().endswith(f'.{ext}')]
        if len(matches) == 1:
            return os.path.join(video_dir_path, matches[0]), ext
        elif len(matches) > 1:
            raise ValueError(f'Multiple .{ext} files found in {video_dir_path}: {matches}')
    raise FileNotFoundError(f'No supported video file (.txt, .xlsx, .xls) found in: {video_dir_path}')


def _normalise_video_df(raw_df):
    missing = [c for c in _VIDEO_REQUIRED_COLS if c not in raw_df.columns]
    if missing:
        raise ValueError(f'Video file missing columns: {missing}. Found: {list(raw_df.columns)}')
    cleaned_df = raw_df[_VIDEO_REQUIRED_COLS].copy()

    def _normalise_hmsf(series):
        # openpyxl sometimes returns this column as timedelta64 (Excel time-of-day
        # format) rather than a plain HH:MM:SS.ffffff string -- handle both.
        if pd.api.types.is_timedelta64_dtype(series):
            return pd.Timestamp('1900-01-01') + series
        s = series.astype(str).str.strip()
        missing_fraction = ~s.str.contains(r'\.', regex=True)
        s[missing_fraction] = s[missing_fraction] + '.000'
        return pd.to_datetime(s, format='%H:%M:%S.%f')

    cleaned_df['datetime'] = _normalise_hmsf(cleaned_df['Time_Relative_hmsf'])
    cleaned_df['Duration_sf'] = pd.to_numeric(cleaned_df['Duration_sf'], errors='coerce')
    return cleaned_df


def _load_video_txt(file_path):
    return pd.read_csv(file_path, sep=';', quotechar='"', encoding='utf-16')


def _load_video_excel(file_path, ext):
    engine = 'xlrd' if ext == 'xls' else 'openpyxl'
    raw_df = pd.read_excel(file_path, sheet_name=0, engine=engine)
    raw_df.columns = raw_df.columns.str.strip()
    return raw_df


def parse_video_event_log(file_path, file_ext):
    if file_ext == 'txt':
        raw_df = _load_video_txt(file_path)
    elif file_ext in ('xlsx', 'xls'):
        raw_df = _load_video_excel(file_path, file_ext)
    else:
        raise ValueError(f'Unsupported video file extension: .{file_ext}')
    return _normalise_video_df(raw_df)


def process_video_events(cleaned_df):
    puff_events = cleaned_df[
        (cleaned_df['Event_Type'].isin(['State start', 'State stop'])) &
        (cleaned_df['Behavior'].str.lower() == 'puff lip')
    ].copy().sort_values('datetime')

    puff_periods = []
    for _, event in puff_events.iterrows():
        if event['Event_Type'] == 'State start':
            start = event['datetime']
            end = start + timedelta(seconds=event['Duration_sf'])
            puff_periods.append((start, end))

    obstruction_events = cleaned_df[
        (cleaned_df['Event_Type'].isin(['State start', 'State stop'])) &
        (cleaned_df['Behavior'].str.lower() == 'obstruction')
    ].copy().sort_values('datetime')

    obstruction_periods = []
    for _, event in obstruction_events.iterrows():
        if event['Event_Type'] == 'State start':
            start = event['datetime']
            end = start + timedelta(seconds=event['Duration_sf'])
            obstruction_periods.append((start, end))

    if not puff_periods:
        return (pd.DataFrame(), np.array([], dtype=int), pd.DataFrame(), np.array([], dtype=int), 0)

    all_times = [p[0] for p in puff_periods] + [p[1] for p in puff_periods]
    if obstruction_periods:
        all_times += [p[0] for p in obstruction_periods] + [p[1] for p in obstruction_periods]

    base_time = min(all_times)
    last_time = max(all_times)
    total_frames = int(round((last_time - base_time).total_seconds() * FRAME_RATE)) + 1

    def _to_frame(dt):
        return int(round((dt - base_time).total_seconds() * FRAME_RATE))

    camera_binary = np.zeros(total_frames, dtype=int)
    obstruction_binary = np.zeros(total_frames, dtype=int)

    for start, end in puff_periods:
        s = _to_frame(start)
        e = min(_to_frame(end), total_frames - 1)
        camera_binary[s:e + 1] = 1

    for start, end in obstruction_periods:
        s = _to_frame(start)
        e = min(_to_frame(end), total_frames - 1)
        obstruction_binary[s:e + 1] = 1

    return (pd.DataFrame(), camera_binary, pd.DataFrame(), obstruction_binary, total_frames)


# ---------------------------------------------------------------
# Device parsing
# ---------------------------------------------------------------

def parse_device_event_log(file_path):
    data = []
    with open(file_path, 'r') as file:
        for line in file:
            match = re.match(
                r'\s*(PUFF|TOUCH)\s+(\d{4}-\d{2}-\d{2}) '
                r'(\d{2}:\d{2}:\d{2}\.\d+)-(\d{2}:\d{2}:\d{2}\.\d+)\s+(\d+\.\d+)',
                line)
            if match:
                event, date_part, start_time, end_time, duration = match.groups()
                start_time = datetime.strptime(start_time, "%H:%M:%S.%f").time()
                end_time = datetime.strptime(end_time, "%H:%M:%S.%f").time()
                duration_sec = float(duration) / 1000
                data.append([event, start_time, end_time, duration_sec])

    df = pd.DataFrame(data, columns=["Event", "Start Time", "End Time", "Duration (s)"])
    all_starts = df["Start Time"].apply(
        lambda t: t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6)
    session_start_sec = float(all_starts.min())
    return df[df["Event"] == "PUFF"].copy(), session_start_sec


def generate_device_binary_array(device_events_df, session_start_sec):
    if device_events_df.empty:
        return np.array([], dtype=int), 0

    def _to_sec(t):
        return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6

    start_frames = ((device_events_df["Start Time"].apply(_to_sec) - session_start_sec)
                     * FRAME_RATE).round().astype(int)
    end_frames = ((device_events_df["End Time"].apply(_to_sec) - session_start_sec)
                   * FRAME_RATE).round().astype(int)

    total_frames = int(end_frames.max()) + 1
    device_binary = np.zeros(total_frames, dtype=int)
    for s, e in zip(start_frames, end_frames):
        s = max(int(s), 0)
        e = min(int(e), total_frames - 1)
        device_binary[s:e + 1] = 1
    return device_binary, total_frames


def build_unified_frame_arrays(camera_binary, obstruction_binary, device_binary, n_cam_frames, n_dev_frames):
    N = max(n_cam_frames, n_dev_frames)
    cam = np.zeros(N, dtype=int)
    cam[:len(camera_binary)] = camera_binary
    fri = np.zeros(N, dtype=int)
    fri[:len(device_binary)] = device_binary
    obs = np.zeros(N, dtype=int)
    obs[:len(obstruction_binary)] = obstruction_binary
    return cam, fri, obs


def get_puffs(signal, obstruction_mask=None):
    signal = np.asarray(signal)
    edges = np.diff(signal)
    starts = np.where(edges == 1)[0] + 1
    ends = np.where(edges == -1)[0] + 1
    if signal[0] == 1:
        starts = np.insert(starts, 0, 0)
    if signal[-1] == 1:
        ends = np.append(ends, len(signal))
    if len(ends) < len(starts):
        ends = np.append(ends, len(signal))
    elif len(ends) > len(starts):
        starts = np.insert(starts, 0, 0)
    puffs = list(zip(starts, ends))
    if obstruction_mask is not None:
        obstruction_mask = np.asarray(obstruction_mask).astype(bool)
        puffs = [(s, e) for s, e in puffs if not obstruction_mask[s:e].any()]
    return puffs


def fft_correlate_full(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n = len(a) + len(b) - 1
    nfft = 1 << (n - 1).bit_length()
    A = np.fft.rfft(a, nfft)
    B = np.fft.rfft(b[::-1], nfft)
    res = np.fft.irfft(A * B, nfft)[:n]
    return np.round(res)


# ---------------------------------------------------------------
# Reconciled matching: TP counted on the CAMERA (true-puff) side
# ---------------------------------------------------------------

def match_puffs(camera_signal, friends_signal, fs, obstruction_mask=None, tolerance_sec=0.5):
    """
    Returns camera_puffs, friends_puffs, camera_matched (bool per true puff),
    friends_target (camera index each FRIENDS puff matched, or None).
    """
    camera_puffs = get_puffs(camera_signal, obstruction_mask=obstruction_mask)
    friends_puffs = get_puffs(friends_signal, obstruction_mask=obstruction_mask)
    tolerance_samples = int(tolerance_sec * fs)

    camera_matched = [False] * len(camera_puffs)
    friends_target = [None] * len(friends_puffs)

    for j, (fr_s, fr_e) in enumerate(friends_puffs):
        for i, (cs, ce) in enumerate(camera_puffs):
            if not ((ce + tolerance_samples) <= (fr_s - tolerance_samples) or
                    (fr_e + tolerance_samples) <= (cs - tolerance_samples)):
                camera_matched[i] = True
                friends_target[j] = i
                break

    return camera_puffs, friends_puffs, camera_matched, friends_target


def precision_recall_f1(tp, fn, fp):
    precision = tp / (tp + fp) if (tp + fp) > 0 else np.nan
    recall = tp / (tp + fn) if (tp + fn) > 0 else np.nan
    if precision and recall and not np.isnan(precision) and not np.isnan(recall) and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = np.nan
    return precision, recall, f1


# ---------------------------------------------------------------
# Participant-cluster bootstrap CI (percentile + BCa), pooled and macro.
# Resamples the 22 participants with replacement; identical method used
# throughout this pipeline (Script2) and matching the bench-testing
# coauthor's device_bootstrap.py.
# ---------------------------------------------------------------

def _pooled_prf(M):
    """M: (n, 3) array of [TP, FN, FP] rows, one per participant. Sums
    counts across the (resampled) participants before taking the ratio
    -- the pooled (micro-averaged) definition."""
    tp, fn, fp = M.sum(0)
    p = tp / (tp + fp) if (tp + fp) > 0 else np.nan
    r = tp / (tp + fn) if (tp + fn) > 0 else np.nan
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else np.nan
    return np.array([p, r, f1])


def _macro_prf(R):
    """R: (n, 3) array of [precision, recall, f1] rows, one per
    participant. Mean of the (resampled) participants' own ratios --
    the macro (unweighted participant-average) definition."""
    return np.nanmean(R, axis=0)


def _bca(theta_hat, boot, jack):
    """Bias-corrected and accelerated interval -- identical formula used
    throughout this pipeline (Script2) and in device_bootstrap.py."""
    z0 = stats.norm.ppf((boot < theta_hat).mean())
    jm = jack.mean()
    a = ((jm - jack) ** 3).sum() / (6 * (((jm - jack) ** 2).sum()) ** 1.5)
    out = []
    for q in (0.025, 0.975):
        z = stats.norm.ppf(q)
        adj = stats.norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))
        out.append(np.percentile(boot, 100 * adj))
    return out


def bootstrap_pooled_and_macro_ci(df):
    """Returns (pooled_ci, macro_ci), each a dict keyed 'Precision'/'Recall'/'F1'
    -> (lower, upper), computed from the per-participant TP/FN/FP and
    precision/recall/f1 columns of df via BCa bootstrap (B replicates,
    resampling participants with replacement)."""
    n = len(df)
    labels = ['Precision', 'Recall', 'F1']
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, n, size=(B, n))

    M = df[['TP', 'FN', 'FP']].values.astype(float)
    pt_pooled = _pooled_prf(M)
    boot_pooled = np.array([_pooled_prf(M[i]) for i in idx])
    jack_pooled = np.array([_pooled_prf(np.delete(M, i, 0)) for i in range(n)])

    R = df[['precision', 'recall', 'f1']].values.astype(float)
    pt_macro = _macro_prf(R)
    boot_macro = np.array([_macro_prf(R[i]) for i in idx])
    jack_macro = np.array([_macro_prf(np.delete(R, i, 0)) for i in range(n)])

    pooled_ci, macro_ci = {}, {}
    for k, lab in enumerate(labels):
        pooled_ci[lab] = (pt_pooled[k],) + tuple(_bca(pt_pooled[k], boot_pooled[:, k], jack_pooled[:, k]))
        macro_ci[lab] = (pt_macro[k],) + tuple(_bca(pt_macro[k], boot_macro[:, k], jack_macro[:, k]))
    return pooled_ci, macro_ci


# ---------------------------------------------------------------
# Per-participant pipeline
# ---------------------------------------------------------------

def run_participant(participant, participant_dir_path):
    video_dir_path = os.path.join(participant_dir_path, 'VIDEO_DATA')
    video_input_file, video_ext = find_video_file(video_dir_path)
    device_dir_path = os.path.join(participant_dir_path, 'DEVICE_DATA')
    device_files = [f for f in os.listdir(device_dir_path) if f.endswith('.txt')]
    device_input_file = os.path.join(device_dir_path, device_files[0])

    video_cleaned_df = parse_video_event_log(video_input_file, video_ext)
    (_, camera_binary, _, obstruction_binary, n_cam_frames) = process_video_events(video_cleaned_df)

    device_events_df, session_start_sec = parse_device_event_log(device_input_file)
    filtered_device_events_df = device_events_df[device_events_df['Duration (s)'] > MIN_PUFF_DURATION]
    device_binary, n_dev_frames = generate_device_binary_array(filtered_device_events_df, session_start_sec)

    camera_signal, friends_signal, obstruction_mask = build_unified_frame_arrays(
        camera_binary, obstruction_binary, device_binary, n_cam_frames, n_dev_frames)

    fs = FRAME_RATE
    N = len(camera_signal)

    xcorr_vals = fft_correlate_full(friends_signal, camera_signal)
    lags = np.arange(-len(camera_signal) + 1, len(friends_signal))
    best_lag = lags[np.argmax(xcorr_vals)]

    aligned_friends_signal = np.zeros_like(friends_signal)
    if best_lag > 0:
        aligned_friends_signal[:N - best_lag] = friends_signal[best_lag:]
    elif best_lag < 0:
        aligned_friends_signal[-best_lag:] = friends_signal[:N + best_lag]
    else:
        aligned_friends_signal = friends_signal.copy()

    camera_puffs, friends_puffs, camera_matched, friends_target = match_puffs(
        camera_signal, aligned_friends_signal, fs,
        obstruction_mask=obstruction_mask, tolerance_sec=TOLERANCE_SEC)

    true_n = len(camera_puffs)
    tp = sum(camera_matched)                       # unique true puffs detected
    fn = true_n - tp
    fp = sum(1 for t in friends_target if t is None)  # FRIENDS puffs matching nothing

    # sanity check: this must ALWAYS hold by construction
    assert tp + fn == true_n, (
        f'{participant}: TP+FN ({tp}+{fn}={tp+fn}) != total true puffs ({true_n})')

    precision, recall, f1 = precision_recall_f1(tp, fn, fp)

    # fragmentation diagnostic: true puffs matched by >1 FRIENDS puff
    target_counts = Counter(t for t in friends_target if t is not None)
    fragmented = {i: c for i, c in target_counts.items() if c > 1}
    n_fragmented_true_puffs = len(fragmented)
    n_extra_fragment_detections = sum(c - 1 for c in fragmented.values())
    old_style_hits = sum(1 for t in friends_target if t is not None)  # original (uncorrected) count

    # ---- duration stats, same definitions as Thermistor_Data_Puff_Analysis_v2.py ----
    cam_durs = [(ce - cs) / fs for cs, ce in camera_puffs]
    fri_durs = [(fe - fs_) / fs for fs_, fe in friends_puffs]
    avg_camera_puff_duration = float(np.mean(cam_durs)) if cam_durs else 0.0
    avg_friends_puff_duration = float(np.mean(fri_durs)) if fri_durs else 0.0

    hit_durations_camera = [(ce - cs) / fs for i, (cs, ce) in enumerate(camera_puffs) if camera_matched[i]]
    hit_durations_friends = [(fe - fs_) / fs for j, (fs_, fe) in enumerate(friends_puffs) if friends_target[j] is not None]
    avg_hit_duration_camera = float(np.mean(hit_durations_camera)) if hit_durations_camera else 0.0
    avg_hit_duration_friends = float(np.mean(hit_durations_friends)) if hit_durations_friends else 0.0

    return {
        'participant': participant,
        'best_lag_frames': int(best_lag),
        'best_lag_sec': round(best_lag / fs, 3),
        'true_puffs': true_n,
        'friends_puffs': len(friends_puffs),
        'avg_camera_puff_duration': round(avg_camera_puff_duration, 3),
        'avg_friends_puff_duration': round(avg_friends_puff_duration, 3),
        'TP': tp,
        'FN': fn,
        'FP': fp,
        'avg_hit_duration_camera': round(avg_hit_duration_camera, 3),
        'avg_hit_duration_friends': round(avg_hit_duration_friends, 3),
        'old_hits_uncorrected': old_style_hits,
        'fragmented_true_puffs': n_fragmented_true_puffs,
        'extra_fragment_detections': n_extra_fragment_detections,
        'precision': precision,
        'recall': recall,
        'f1': f1,
    }


# ---------------------------------------------------------------
# Mode helper (rounded to 3 dp; returns comma-joined list if multi-modal)
# ---------------------------------------------------------------

def mode_str(series, ndigits=3):
    rounded = series.round(ndigits)
    modes = rounded.mode()
    return ', '.join(f'{m:.{ndigits}f}' for m in modes)


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main(participant_dir, out_xlsx_path):
    sub_folders = sorted([
        name for name in os.listdir(participant_dir)
        if os.path.isdir(os.path.join(participant_dir, name))
    ])

    rows = []
    errors = []
    for participant in sub_folders:
        print(f'Processing {participant} ...')
        try:
            res = run_participant(participant, os.path.join(participant_dir, participant))
            rows.append(res)
        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()
            errors.append({'Participant': participant, 'Error': str(e)})

    df = pd.DataFrame(rows)

    # ---- per-participant table: SAME column set/order as the original
    # Participant_Summary_0.4_10_v1.xlsx / Thermistor_Data_Puff_Analysis_v2.py
    # output, with Hits/Misses/False Alarms/Precision/Recall/F1 now using the
    # reconciled (TP+FN==true puffs, by construction) definition. Diagnostic
    # columns explaining the reconciliation are appended at the end.
    per_participant = pd.DataFrame({
        'Participant': df['participant'],
        'Device File Type': 'duration',
        'Best Lag (frames)': df['best_lag_frames'],
        'Best Lag (sec)': df['best_lag_sec'],
        'Camera Puff Count': df['true_puffs'],
        'FRIENDS Puff Count': df['friends_puffs'],
        'Camera Avg Puff Duration': df['avg_camera_puff_duration'],
        'FRIENDS Avg Puff Duration': df['avg_friends_puff_duration'],
        'Hits': df['TP'],
        'Misses': df['FN'],
        'False Alarms': df['FP'],
        'Precision': df['precision'].round(4),
        'Recall': df['recall'].round(4),
        'F1 Score': df['f1'].round(4),
        'Avg Hit Duration (Camera)': df['avg_hit_duration_camera'],
        'Avg Hit Duration (FRIENDS)': df['avg_hit_duration_friends'],
        # -- reconciliation diagnostics (new) --
        'Hits + Misses (must equal Camera Puff Count)': df['TP'] + df['FN'],
        'Old uncorrected Hits (pre-fix)': df['old_hits_uncorrected'],
        'Fragmented true puffs': df['fragmented_true_puffs'],
        'Extra fragment detections': df['extra_fragment_detections'],
    })

    # global assertion: Hits+Misses must equal Camera Puff Count for every row
    bad = per_participant[
        per_participant['Hits + Misses (must equal Camera Puff Count)'] != per_participant['Camera Puff Count']]
    if len(bad):
        raise AssertionError(f'Reconciliation failed for participants:\n{bad}')

    # ---- pooled (micro-average) ----
    TP, FN, FP = int(df['TP'].sum()), int(df['FN'].sum()), int(df['FP'].sum())
    true_total = int(df['true_puffs'].sum())
    assert TP + FN == true_total, f'Pooled check failed: {TP}+{FN} != {true_total}'
    p_pool, r_pool, f1_pool = precision_recall_f1(TP, FN, FP)

    # ---- pooled and macro 95% CI, BCa participant-cluster bootstrap ----
    pooled_ci, macro_ci = bootstrap_pooled_and_macro_ci(df)

    pooled_summary = pd.DataFrame([{
        'Total Camera Puff Count': true_total,
        'Total FRIENDS Puff Count': int(df['friends_puffs'].sum()),
        'Total Hits': TP,
        'Total Misses': FN,
        'Total False Alarms': FP,
        'Hits + Misses': TP + FN,
        'Check (Hits+Misses == Camera Puff Count)': 'OK' if TP + FN == true_total else 'MISMATCH',
        'Pooled Precision': round(p_pool, 4),
        'Pooled Precision 95% CI Lower (BCa)': round(pooled_ci['Precision'][1], 4),
        'Pooled Precision 95% CI Upper (BCa)': round(pooled_ci['Precision'][2], 4),
        'Pooled Recall': round(r_pool, 4),
        'Pooled Recall 95% CI Lower (BCa)': round(pooled_ci['Recall'][1], 4),
        'Pooled Recall 95% CI Upper (BCa)': round(pooled_ci['Recall'][2], 4),
        'Pooled F1': round(f1_pool, 4),
        'Pooled F1 95% CI Lower (BCa)': round(pooled_ci['F1'][1], 4),
        'Pooled F1 95% CI Upper (BCa)': round(pooled_ci['F1'][2], 4),
        'Total fragmented true puffs': int(df['fragmented_true_puffs'].sum()),
        'Total extra fragment detections': int(df['extra_fragment_detections'].sum()),
        'Total old uncorrected Hits (pre-fix)': int(df['old_hits_uncorrected'].sum()),
    }])

    # ---- macro stats: mean / median / mode / SD across the 22 participants ----
    macro_stats = pd.DataFrame({
        'Metric': ['Precision', 'Recall', 'F1'],
        'Mean': [df['precision'].mean(), df['recall'].mean(), df['f1'].mean()],
        'Macro 95% CI Lower (BCa)': [macro_ci['Precision'][1], macro_ci['Recall'][1], macro_ci['F1'][1]],
        'Macro 95% CI Upper (BCa)': [macro_ci['Precision'][2], macro_ci['Recall'][2], macro_ci['F1'][2]],
        'Median': [df['precision'].median(), df['recall'].median(), df['f1'].median()],
        'Mode': [mode_str(df['precision']), mode_str(df['recall']), mode_str(df['f1'])],
        'Std Dev': [df['precision'].std(), df['recall'].std(), df['f1'].std()],
        'Min': [df['precision'].min(), df['recall'].min(), df['f1'].min()],
        'Max': [df['precision'].max(), df['recall'].max(), df['f1'].max()],
    })
    for col in ['Mean', 'Macro 95% CI Lower (BCa)', 'Macro 95% CI Upper (BCa)', 'Median', 'Std Dev', 'Min', 'Max']:
        macro_stats[col] = macro_stats[col].round(4)

    with pd.ExcelWriter(out_xlsx_path) as writer:
        per_participant.to_excel(writer, sheet_name='Per_Participant', index=False)
        pooled_summary.to_excel(writer, sheet_name='Pooled_Summary', index=False)
        macro_stats.to_excel(writer, sheet_name='Mean_Median_Mode', index=False)
        if errors:
            pd.DataFrame(errors).to_excel(writer, sheet_name='Errors', index=False)

    print('\n=== DONE ===')
    print(f'Written: {out_xlsx_path}')
    print(f'\nPooled: TP={TP}  FN={FN}  FP={FP}  TP+FN={TP+FN} (true puffs={true_total})')
    print(f'Pooled Precision={p_pool:.4f} [{pooled_ci["Precision"][1]:.4f}, {pooled_ci["Precision"][2]:.4f}]  '
          f'Recall={r_pool:.4f} [{pooled_ci["Recall"][1]:.4f}, {pooled_ci["Recall"][2]:.4f}]  '
          f'F1={f1_pool:.4f} [{pooled_ci["F1"][1]:.4f}, {pooled_ci["F1"][2]:.4f}]  '
          f'(95% BCa bootstrap CI, B={B:,}, seed={SEED})')
    print(f'Macro Precision={macro_ci["Precision"][0]:.4f} [{macro_ci["Precision"][1]:.4f}, {macro_ci["Precision"][2]:.4f}]  '
          f'Recall={macro_ci["Recall"][0]:.4f} [{macro_ci["Recall"][1]:.4f}, {macro_ci["Recall"][2]:.4f}]  '
          f'F1={macro_ci["F1"][0]:.4f} [{macro_ci["F1"][1]:.4f}, {macro_ci["F1"][2]:.4f}]  '
          f'(95% BCa bootstrap CI, B={B:,}, seed={SEED})')
    print('\nMean/Median/Mode:')
    print(macro_stats.to_string(index=False))

    return per_participant, pooled_summary, macro_stats


if __name__ == '__main__':
    # Relative to this script's own location, so the defaults work
    # regardless of who clones the repo or where it's placed on disk.
    THIS_DIR = os.path.dirname(os.path.abspath(__file__))
    Participant_Dir = os.path.join(THIS_DIR, '..', 'Participant Data')
    Out_Xlsx = os.path.join(THIS_DIR, '..', 'Results', 'Reconciled_Detection_Metrics_Summary.xlsx')
    if len(sys.argv) >= 3:
        Participant_Dir = sys.argv[1]
        Out_Xlsx = sys.argv[2]
    main(Participant_Dir, Out_Xlsx)