FRIENDS Human Laboratory Study -- Analysis Code
=================================================

This folder contains the analysis pipeline for the human laboratory
validation study reported in the FRIENDS manuscript (IEEE TIM). All
scripts read raw data from "../Participant Data" (one subfolder per
participant, each with DEVICE_DATA and VIDEO_DATA) and write results to
"../Results".

Requirements: Python 3.10+, pandas, numpy, scipy, openpyxl, matplotlib.
Install with:
    pip install pandas numpy scipy openpyxl matplotlib

All later scripts import Script1's functions directly (via importlib), so
Script1 does not need to be run first -- Script2, Script3, Script4, and
Script5 each independently re-derive whatever they need from the raw
Participant Data. Every script is self-contained and reproducible from
source data alone; none of them read a pre-existing summary spreadsheet.

IMPORTANT: each script's __main__ block has a default input/output path
hardcoded for the original author's machine. Always pass explicit paths
on the command line (see below) rather than relying on the defaults.

Only scripts that produce a number actually reported in the manuscript
are kept here. A closed-form (Cochran ratio-of-totals) implementation of
the pooled CI existed earlier and matched the professor's originally
specified formula exactly, but was removed once the manuscript switched
to reporting the bootstrap/BCa CI throughout (matching the method used
for bench lifecycle testing) -- see the Provenance note in the top-level
ReadMe.txt if you need to recover that method.


------------------------------------------------------------------------
Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py
------------------------------------------------------------------------
What it does:
  Parses each participant's video annotation log (ground-truth "puff lip"
  events) and FRIENDS device log (PUFF events, >0.4s duration filter),
  aligns the two signals by FFT cross-correlation, and computes the
  reconciled confusion matrix: TP = unique true (video) puffs matched by
  >=1 FRIENDS puff; FN = true puffs matched by none; FP = FRIENDS puffs
  matched to no true puff (TP + FN always equals total true puffs, by
  construction).

Manuscript numbers this produces (Laboratory Validation with Human
Participants section):
  - 866 video-coded puffs, 888 FRIENDS-detected puffs
  - 799 TP, 67 FN, 73 FP (16 = 888 - 799 - 73 fragmentation duplicates)

Run:
    python Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py "<Participant Data dir>" "<output .xlsx path>"

Output: an .xlsx with Per_Participant, Pooled_Summary, and
Mean_Median_Mode sheets.
Reference output: ../Results/Reconciled_Detection_Metrics_Summary.xlsx


------------------------------------------------------------------------
Script2_Touch_Sensor_Analysis_Reconciled.py
------------------------------------------------------------------------
What it does:
  Answers: "of the FRIENDS puffs in the reconciled confusion matrix
  (Script1), how many temporally overlap a touch-sensor activation, and
  what happens to precision/recall/F1 if detection is gated on touch
  overlap?" Reuses Script1's own functions unmodified for puff counting;
  touch overlap is decided on the FRIENDS device's own clock (not the
  camera-aligned frame grid), since touch and puff events share one clock
  and the camera-alignment lag must not be applied to a device-internal
  comparison. A prior touch-analysis script was deleted from this folder
  because it independently reimplemented device-signal binarization and
  silently dropped puffs in dense-puffing participants (verified bug) --
  do not recreate that approach.

Manuscript numbers this produces:
  - 322 of 888 FRIENDS puffs (36%) overlapped a touch-sensor activation
  - Touch-gated: Precision 93%, Recall 34%, mean F1 50%

Run:
    python Script2_Touch_Sensor_Analysis_Reconciled.py "<Participant Data dir>" "<output .xlsx path>"

Output: an .xlsx with Per_Participant and Pooled_Summary sheets (baseline
confusion matrix + touch-gated confusion matrix, side by side).
Reference output: ../Results/Touch_Sensor_Analysis_Reconciled.xlsx


------------------------------------------------------------------------
Script3_Duration_Correlation_BlandAltman.py
------------------------------------------------------------------------
What it does:
  Pearson correlation and Bland-Altman agreement analysis between
  video-coded and FRIENDS-measured puff duration, using only correctly
  matched (hit) puffs -- the only definition for which Bland-Altman's
  "two measurements of the same event" assumption actually holds (an
  "all puffs" comparison would mix in FRIENDS false-positive durations
  and camera missed-puff durations that have no counterpart in the other
  stream; that alternative was considered and rejected -- see the
  script's header comment and its Method output sheet).

Manuscript numbers this produces:
  - Mean video duration 2.57 +/- 0.83 s vs. FRIENDS 2.05 +/- 0.59 s
  - Pearson r = 0.87, p < 0.001
  - Bland-Altman: mean bias +0.53 s, 95% limits of agreement -0.33 to
    +1.38 s, proportional bias r = 0.59, p = 0.004
  - Fig. 9 (Bland-Altman plot)

Run:
    python Script3_Duration_Correlation_BlandAltman.py "<Participant Data dir>" "<output directory>"

Output: Duration_Correlation_BlandAltman.xlsx (Per_Participant_Durations,
Summary, Method sheets) plus BlandAltman_PuffDuration.png (Fig. 9) and
Correlation_PuffDuration.png.
Reference output: ../Results/Duration_Correlation_BlandAltman/


------------------------------------------------------------------------
Script4_Human_Study_Cluster_Bootstrap_CI.py
------------------------------------------------------------------------
What it does:
  Single script for all bootstrap-based confidence intervals in the human
  study: computes BOTH the pooled and the macro Precision/Recall/F1
  target, each with its own resample-and-recompute bootstrap loop, and
  reports both a percentile and a BCa (bias-corrected and accelerated)
  interval for each. Mirrors device_bootstrap.py (bench lifecycle
  testing, "CI Code and description/bootstrapcode/") exactly, with
  participant substituted for device as the resampling cluster. BCa is
  the version actually used in the manuscript, matching the method your
  bench-testing coauthor used for the bench-lifecycle CIs.

  POOLED -- sum TP/FN/FP across the resampled participants FIRST, then
  take the ratio (e.g. Precision = SumTP / (SumTP+SumFP)) -- weights each
  participant by their own puff count.

  MACRO -- compute each participant's OWN ratio first (Precision_j =
  TP_j/(TP_j+FP_j), etc.), then take the plain UNWEIGHTED mean across the
  22 participants -- every participant counts equally regardless of puff
  count.

  These are genuinely different statistics (a puff-weighted average of
  the 22 participants' own ratios collapses algebraically back to the
  pooled estimate), so each has its own bootstrap loop -- see the
  script's header comment and Bootstrap_Method_Description.docx
  (Manuscript/) for the full derivation.

Manuscript numbers this produces:
  - Pooled: Precision 91.6% (95% CI 80.7-96.4), Recall 92.3% (95% CI
    81.5-97.6), F1 91.9% (95% CI 84.1-96.0) -- BCa
  - Macro: Precision 93.4% (95% CI 83.6-96.9), Recall 92.4% (95% CI
    83.7-97.3), F1 92.1% (95% CI 84.2-96.2) -- BCa

Run:
    python Script4_Human_Study_Cluster_Bootstrap_CI.py "<Participant Data dir>" "<output .xlsx path>"

Output: an .xlsx with Per_Participant_Data (TP/FN/FP + each participant's
own ratios), Pooled_Bootstrap_Summary, Macro_Bootstrap_Summary (both:
estimate, percentile CI, BCa CI, n, B, seed), and Method sheets.
Reference output: ../Results/Human_Study_Cluster_Bootstrap_CI.xlsx


------------------------------------------------------------------------
Script5_Duration_Distribution_and_Threshold_Sensitivity.py
------------------------------------------------------------------------
What it does:
  Addresses Comment 1.7 (threshold rationale / sensitivity analysis).
  Two parts, both reusing Script1's own functions unmodified:

  PART A -- every individual camera puff duration (866, video-coded
  ground truth, no threshold applied) and every individual FRIENDS puff
  duration (888, at the 0.4 s production threshold used everywhere else
  in the manuscript) -- not participant averages. Reports n, mean, SD,
  range, and 95% CI (t-interval) for each, and saves a histogram for
  each (camera histogram marks the 0.4 s threshold to show it sits below
  the empirical floor of camera puff durations).

  PART B -- pooled precision/recall/F1 with Script1's MIN_PUFF_DURATION
  swept across 0.0, 0.2, 0.4, and 0.6 s (0.0 s = no filter), pooling
  TP/FN/FP across all 22 participants at each threshold.

Manuscript numbers this produces:
  - Camera duration: n=866, mean=2.38 s, SD=0.96 s, range=[0.60, 8.00] s,
    95% CI=[2.31, 2.44] s
  - FRIENDS duration: n=888, mean=1.87 s, SD=0.89 s, range=[0.44, 8.04] s,
    95% CI=[1.81, 1.93] s
  - Threshold sweep (pooled P/R/F1): 0.0 s -> 0.874/0.928/0.900;
    0.2 s -> 0.874/0.927/0.900; 0.4 s -> 0.916/0.923/0.919 (production,
    matches Script1/Script4 exactly); 0.6 s -> 0.935/0.923/0.929

Run:
    python Script5_Duration_Distribution_and_Threshold_Sensitivity.py "<Participant Data dir>" "<output directory>"

Output: Duration_Distribution_and_Threshold_Sensitivity.xlsx
(Duration_Summary, Per_Puff_Durations, Threshold_Sensitivity, Method
sheets) plus Histogram_Camera_Puff_Duration.png,
Histogram_FRIENDS_Puff_Duration.png, and Threshold_Sensitivity_PRF1.png.
Reference output: ../Results/Duration_Distribution_and_Threshold_Sensitivity/


------------------------------------------------------------------------
add_video_annotation_time.py
------------------------------------------------------------------------
Utility script (prompts interactively for an input file path). Adds a
video_annotation_time column to a participant's False-Alarm-puffs sheet
by offsetting each false-alarm start time from the video's base
timestamp. Not tied to any specific number reported in the manuscript --
a data-preparation aid, not part of the five analyses above.


------------------------------------------------------------------------
Quick reference: manuscript number -> script
------------------------------------------------------------------------
866 / 888 / 799 TP / 67 FN / 73 FP ................... Script1
Pooled Precision/Recall/F1, BCa 95% CI ............... Script4
Macro Precision/Recall/F1, BCa 95% CI ................ Script4
Camera/FRIENDS duration distribution + histograms .... Script5
Threshold sensitivity (0/0.2/0.4/0.6 s) .............. Script5
322/888 (36%) touch overlap; touch-gated P/R/F1 ...... Script2
2.57+/-0.83 s / 2.05+/-0.59 s, r=0.87, p<0.001 ........ Script3
Bland-Altman bias +0.53 s, LoA [-0.33, 1.38] .......... Script3
Fig. 9 (Bland-Altman plot) ............................ Script3
