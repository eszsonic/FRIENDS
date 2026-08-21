FRIENDS Human Laboratory Study -- Code
======================================

Scope: human laboratory validation only (22 participants).

Note: BLAND_ALTMAN_FIGURE/ (bland_altman_human.py and its output) is a
work in progress -- the finalized script and figure for the human study's
duration correlation / Bland-Altman analysis will be added to this
pipeline later. Not yet documented below.

Both scripts take zero arguments by default: they locate "Participant
Data" and write into "Results" using paths relative to the scripts' own
location (Codes/), so the pipeline runs unmodified regardless of where
the repo is cloned. Optionally pass two positional arguments to override
(participant_dir, output_path):

    python Script1_0.4sec_threshold_performance_metrics.py
    python Script2_different_threshold_sensitivity_analysis.py


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

Also computes pooled (micro-averaged) and macro (participant-averaged)
Precision/Recall/F1, each with a 95% BCa (bias-corrected and accelerated)
bootstrap CI -- participant-cluster resampling, B=10,000 replicates,
seed=12345.

Output: Results/Reconciled_Detection_Metrics_Summary.xlsx
    - Per_Participant   per-participant counts, durations, P/R/F1
    - Pooled_Summary    pooled TP/FN/FP and pooled P/R/F1 with 95% CI
    - Mean_Median_Mode  macro P/R/F1 (mean/median/mode/SD/min/max) with 95% CI
    - Errors            (only if any participant failed to process)

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
Imports Script1 unmodified and re-runs it at each threshold in the sweep.

    Part A: threshold sensitivity -- pooled Precision/Recall/F1 at
            detection thresholds of 0.0, 0.2, 0.4, and 0.6 s, each with a
            95% BCa bootstrap CI (identical method to Script1's pooled CI,
            so the 0.4 s row matches Script1 exactly).
    Part B: puff duration distribution -- duration of every individual
            camera puff and every individual FRIENDS puff (not
            participant averages) at the 0.4 s production threshold --
            mean, SD, range, 95% CI (t-interval), and a histogram for
            each.

Output: Results/Threshold_Sensitivity_and_Duration_Distribution/
    - Threshold_Sensitivity_and_Duration_Distribution.xlsx
        - Threshold_Sensitivity   Part A table
        - Duration_Summary        Part B summary stats
        - Per_Puff_Durations      Part B raw per-puff durations
        - Method                  method notes
    - Threshold_Sensitivity_PRF1.png
    - Histogram_Camera_Puff_Duration.png
    - Histogram_FRIENDS_Puff_Duration.png

Verified numbers:
    Threshold sensitivity (TP / FN / FP / Precision [CI] / Recall [CI] / F1 [CI]):
      0.0 s: TP=804 FN=62 FP=116  P=0.8739 [0.7582,0.9488]  R=0.9284 [0.8219,0.9775]  F1=0.9003 [0.8224,0.9498]
      0.2 s: TP=803 FN=63 FP=116  P=0.8738 [0.7580,0.9487]  R=0.9273 [0.8217,0.9765]  F1=0.8997 [0.8219,0.9492]
      0.4 s: TP=799 FN=67 FP=73   P=0.9163 [0.8072,0.9635]  R=0.9226 [0.8153,0.9756]  F1=0.9194 [0.8414,0.9597]
      0.6 s: TP=799 FN=67 FP=56   P=0.9345 [0.8533,0.9734]  R=0.9226 [0.8153,0.9756]  F1=0.9285 [0.8585,0.9657]
    Duration distribution (individual puffs, pooled across 22 participants):
      Camera:  n=866  mean=2.3763 s  SD=0.9558 s  range=[0.6000, 8.0000] s  95% CI=[2.3125, 2.4400] s
      FRIENDS: n=888  mean=1.8665 s  SD=0.8935 s  range=[0.4400, 8.0400] s  95% CI=[1.8076, 1.9253] s


Provenance note
---------------
Script2 previously existed as two separate scripts (a threshold-only
script and a duration-only script); these were merged back into one
combined Script2 (Part A + Part B) and the separate scripts, plus their
now-superseded output folders, were deleted. All numbers above were
re-verified against the current script versions before this ReadMe was
written.
