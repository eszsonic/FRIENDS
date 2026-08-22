FRIENDS Human Laboratory Study -- Code
======================================

Scope: human laboratory validation only (22 participants).

Note: BLAND_ALTMAN_FIGURE/ contains only a leftover copy of
Reconciled_Detection_Metrics_Summary.xlsx -- superseded by the canonical
copy in Results/ (see Script1 below) and not part of this pipeline.
Its former scripts (bland_altman_human.py and a stale duplicate of
Script4) have been removed; puff-duration correlation/Bland-Altman is
Script4_Duration_Correlation_BlandAltman.py in this Codes/ folder.

All scripts take zero arguments by default: they locate "Participant
Data" and write into "Results" using paths relative to the scripts' own
location (Codes/), so the pipeline runs unmodified regardless of where
the repo is cloned. Optionally pass two positional arguments to override
(participant_dir, output_path):

    python Script1_0.4sec_threshold_performance_metrics.py
    python Script2_different_threshold_sensitivity_analysis.py
    python Script3_Touch_Sensor_Analysis.py
    python Script4_Duration_Correlation_BlandAltman.py
    python Script5_Puff_Duration_Distribution.py

Scripts 2-5 each import Script1 directly (unmodified) and reuse its
parsing/alignment/matching functions, so every script's numbers are
reproducible from raw Participant Data alone -- no intermediate
spreadsheet is read anywhere in this pipeline.


Script1_0.4sec_threshold_performance_metrics.py
------------------------------------------------
Confusion matrix (camera vs. FRIENDS puff detection) at the manuscript's
production threshold (0.4 s minimum FRIENDS puff duration). Parses the
raw video-coded and device event logs for all 22 participants, aligns
them via FFT cross-correlation, and matches puffs with the reconciled
definition:

    TP = unique true (video) puffs matched by >=1 FRIENDS puff
    FN = true puffs matched by zero FRIENDS puffs      (TP + FN == true puffs, always)
    FP = FRIENDS puffs that matched zero true puffs

Matching tolerance: a camera puff and a FRIENDS puff are matched if they
overlap, or the gap between one's end and the other's start does not
exceed 1.0 s -- implemented as TOLERANCE_SEC = 0.5 s padded independently
onto EACH of the two puff boundaries (camera and FRIENDS), per the
manuscript's methods text verbatim: "a TP was counted ... if it
overlapped [the other event], or the gap between one end and the other's
start did not exceed 1.0 s (a +/-0.5 s tolerance applied to each puff
boundary)." This is intentional, not a bug -- see the comment directly
above the overlap check in match_puffs().

Also computes pooled (micro-averaged) and macro (participant-averaged)
Precision/Recall/F1, each with a 95% BCa (bias-corrected and accelerated)
bootstrap CI -- participant-cluster resampling, B=10,000 replicates,
seed=12345.

If any participant fails to process, main() raises immediately rather than
silently computing aggregates on a partial cohort -- no output file is
written in that case.

Output: Results/Reconciled_Detection_Metrics_Summary.xlsx
    - Per_Participant   per-participant counts, durations, P/R/F1
    - Pooled_Summary    pooled TP/FN/FP and pooled P/R/F1 with 95% CI
    - Mean_Median_Mode  macro P/R/F1 (mean/median/mode/SD/min/max) with 95% CI

Verified manuscript numbers (0.4 s threshold):
    Pooled:  TP=799  FN=67  FP=73   (true puffs=866)
             Precision=0.9163 [0.8072, 0.9635]
             Recall=0.9226    [0.8153, 0.9756]
             F1=0.9194        [0.8414, 0.9597]
    Macro:   Precision=0.9337 [0.8364, 0.9692]
             Recall=0.9242    [0.8372, 0.9733]
             F1=0.9205        [0.8418, 0.9619]
    Fragmentation diagnostic: 16 true puffs detected as >1 FRIENDS puff
    (888 total FRIENDS puffs = 799 TP + 73 FP + 16 extra fragment detections)


Script2_different_threshold_sensitivity_analysis.py
-----------------------------------------------------
Addresses Comment 1.7 (threshold rationale / sensitivity analysis).
Imports Script1 unmodified and re-runs it at each threshold in the sweep:
pooled Precision/Recall/F1 at detection thresholds of 0.0, 0.2, 0.4, and
0.6 s, each with a 95% BCa bootstrap CI (identical method to Script1's
pooled CI, so the 0.4 s row matches Script1 exactly).

Output: Results/Threshold_Sensitivity_Performance_Metrics/
    - Threshold_Sensitivity_Performance_Metrics.xlsx (Threshold_Sensitivity, Method)
    - Threshold_Sensitivity_PRF1.png

Verified numbers (TP / FN / FP / Precision [CI] / Recall [CI] / F1 [CI]):
      0.0 s: TP=804 FN=62 FP=116  P=0.8739 [0.7582,0.9488]  R=0.9284 [0.8219,0.9775]  F1=0.9003 [0.8224,0.9498]
      0.2 s: TP=803 FN=63 FP=116  P=0.8738 [0.7580,0.9487]  R=0.9273 [0.8217,0.9765]  F1=0.8997 [0.8219,0.9492]
      0.4 s: TP=799 FN=67 FP=73   P=0.9163 [0.8072,0.9635]  R=0.9226 [0.8153,0.9756]  F1=0.9194 [0.8414,0.9597]
      0.6 s: TP=799 FN=67 FP=56   P=0.9345 [0.8533,0.9734]  R=0.9226 [0.8153,0.9756]  F1=0.9285 [0.8585,0.9657]


Script3_Touch_Sensor_Analysis.py
-----------------------------------
Addresses Comments 1.6/2.9 (touch-sensor gating). Reuses Script1's exact
pipeline (not reimplemented) to get, per participant, the FRIENDS puffs
that make up the verified confusion matrix, then restricts detection to
the subset that temporally overlaps a touch-sensor activation. Touch and
puff events share the FRIENDS device's own clock, so overlap is decided
in raw device-clock seconds (inverting the cross-correlation shift),
never on the camera-aligned frame grid.

Output: Results/Touch_Sensor_Analysis.xlsx
    - Per_Participant, Pooled_Summary

Verified numbers:
    Baseline (matches Script1): TP=799 FN=67 FP=73  P=0.9163 R=0.9226 F1=0.9194
    Touch overlap: 322 / 888 FRIENDS puffs (36.3%)
    Touch-gated pooled: TP=298 FN=568 FP=22  P=0.9313 R=0.3441 F1=0.5025
    Note: the manuscript states a touch-gated F1 of 0.550 -- this does not
    match either the pooled F1 (0.50, computed from the same P=0.93/R=0.34
    the manuscript reports) or the unweighted per-participant mean F1
    (0.4461 -> 0.45). This is a confirmed manuscript error requiring
    correction, not a script discrepancy.


Script4_Duration_Correlation_BlandAltman.py
-----------------------------------------------
Addresses Comments 1.8/2.8 (puff-duration agreement). Pearson correlation
+ Bland-Altman analysis using participant-level "hits only" mean puff
duration (Avg Hit Duration (Camera) vs Avg Hit Duration (FRIENDS) from
Script1 -- only puffs matched between video and device). This is the only
valid definition for a Bland-Altman comparison: each paired point must be
two measurements of the same event, which "all puffs" would violate by
mixing in FRIENDS false-positive durations and camera missed-puff
durations.

Output: Results/Duration_Correlation_BlandAltman/
    - Duration_Correlation_BlandAltman.xlsx (Per_Participant_Durations, Summary, Method)
    - BlandAltman_PuffDuration.png, Correlation_PuffDuration.png

Duration pairing note: Script1.match_puffs allows multiple FRIENDS
detections to match one fragmented camera puff. run_participant()
aggregates (sums) FRIENDS fragment durations per matched camera puff
before averaging, so Avg Hit Duration (Camera) and Avg Hit Duration
(FRIENDS) are both built from exactly one value per matched (TP) puff --
a true one-to-one comparison (Copilot PR review finding).

Verified numbers (n=22 participants):
    Camera : mean=2.5739 s  SD=0.8348 s  95% CI=[2.2038, 2.9440]
    FRIENDS: mean=2.1023 s  SD=0.6856 s  95% CI=[1.7983, 2.4063]
    Pearson r=0.9431 (p=5.1e-11)
    Bland-Altman bias (Camera-FRIENDS) = +0.4716 s (95% CI +0.3406 to +0.6027)
    95% limits of agreement: -0.1076 to +1.0509 s
    Proportional bias: r=0.5119, p=0.0149
    Note: the manuscript's camera mean duration (2.53 s) is stale -- the
    verified value is 2.57 s (SD 0.83 s is correct). This needs correcting
    in the manuscript. The FRIENDS mean, Pearson r, bias, and LoA above
    also differ from earlier manuscript drafts because of the fragment-
    aggregation fix; the manuscript's duration-agreement numbers need a
    full update to match (r improves from 0.87 to 0.94).


Script5_Puff_Duration_Distribution.py
------------------------------------------
Duration of every individual camera puff and every individual FRIENDS
puff (not participant averages), at the 0.4 s production threshold --
mean, SD, range, 95% CI (t-interval), and a histogram for each. This is
the POOLED individual-puff duration distribution -- a different statistic
from Script4's participant-level "hits only" mean duration; both are
legitimate but answer different questions (same pooled-vs-macro
distinction as Script1's P/R/F1).

Output: Results/Puff_Duration_Distribution/
    - Puff_Duration_Distribution.xlsx (Duration_Summary, Per_Puff_Durations, Method)
    - Histogram_Camera_Puff_Duration.png, Histogram_FRIENDS_Puff_Duration.png

Verified numbers (individual puffs, pooled across 22 participants):
      Camera:  n=866  mean=2.3763 s  SD=0.9558 s  range=[0.6000, 8.0000] s  95% CI=[2.3125, 2.4400] s
      FRIENDS: n=888  mean=1.8665 s  SD=0.8935 s  range=[0.4400, 8.0400] s  95% CI=[1.8076, 1.9253] s


Provenance note
---------------
Script2 and Script5 previously existed merged into one combined script
(threshold sensitivity + duration distribution), then were split apart,
then merged again, then split apart again as the manuscript review
process clarified what each comment actually needed. The current split
(Script2 = threshold sensitivity only, Script5 = duration distribution
only) avoids duplicating the duration-distribution logic between two
scripts. All numbers above were re-verified against the current script
versions before this ReadMe was written.
