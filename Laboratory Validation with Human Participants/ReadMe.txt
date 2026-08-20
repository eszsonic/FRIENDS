FRIENDS Paper -- Lab Data, Code, and Results
==============================================

This folder contains everything for the human laboratory validation
study reported in the FRIENDS manuscript (IEEE TIM): the manuscript
itself, the raw participant data, the analysis code, and the code's
output. It is organized so that every number and figure reported in the
manuscript's "Laboratory Validation with Human Participants" section can
be traced back to the script that produced it and reproduced from the
raw data.

Folder layout
-------------

Manuscript/
    The manuscript and reviewer-response documents:
      - IEEE_TIM_FRIENDS_v17_tracked_Rafi_DH.docx  (manuscript, tracked changes)
      - IEEE_TIM_FRIENDS_v17_tracked_Rafi_DH_8_17_2026.docx  (coauthor's edit
                                                    branch, renamed with today's
                                                    date -- NOT YET reconciled
                                                    with the _DH version above)
      - FRIENDS_Paper_Revision.docx                (revision text/analysis addendum)
      - FRIENDS_point_by_point_response_revised_DH.docx
      - FRIENDS_point_by_point_response_revised_Rafi_DH.docx
      - FRIENDS_point_by_point_response_revised_Rafi_DH_8_17_2026.docx
                                                    (coauthor's edit branch, same
                                                     reconciliation caveat)
      - CI_Methods_Description.docx    (pooled + macro CI methods, for
                                          statistical review)
      - Bootstrap_Method_Description.docx  (participant/device-cluster bootstrap
                                              CI method, for statistical review)
    (Reviewer response and methods documents, not analysis code or data.)

CI Code and description/
    Bench-testing coauthor's bootstrap CI implementation and reference data
    (bootstrapcode/device_bootstrap.py, FRIENDS-Data-V5-CI-corrected.xlsx).
    Script4 (below) mirrors this exact method for the human study, with
    participant substituted for device as the resampling cluster.

Participant Data/
    Raw human laboratory study data, one subfolder per participant
    (e.g. FRIENDS2076), each containing:
      - DEVICE_DATA/        raw FRIENDS device event log (.txt)
      - VIDEO_DATA/         human video annotation of puffs (.txt/.xlsx)
      - OUTPUT_DIR/         per-participant figures/summary (no touch sensor)
      - OUTPUT_TOUCH_DIR/   per-participant figures/summary (with touch sensor)
    See Participant Data/ReadMe.txt for details. This is the sole source
    of truth -- every number in Results/ is derived from these files by
    the scripts in Codes/, not the reverse.

Codes/
    The analysis pipeline (5 scripts, numbered in the order they were
    developed, not a required run order -- each is independently
    self-contained and reads directly from Participant Data/). Only
    scripts that produce a number actually reported in the manuscript are
    kept here -- see the Provenance note below. See Codes/ReadMe.txt for
    what each script computes, which manuscript number/figure it
    produces, and how to run it.
      - Script1_Puff_Analysis_Reconciled_Confusion_Matrix.py
      - Script2_Touch_Sensor_Analysis_Reconciled.py
      - Script3_Duration_Correlation_BlandAltman.py
      - Script4_Human_Study_Cluster_Bootstrap_CI.py
      - Script5_Duration_Distribution_and_Threshold_Sensitivity.py
      - add_video_annotation_time.py  (data-prep utility, not one of the five analyses)

Results/
    The output of the five scripts above -- every file here is
    reproducible by re-running the corresponding script against
    Participant Data/. Nothing in this folder is hand-edited.
      - Reconciled_Detection_Metrics_Summary.xlsx  <- Script1
      - Touch_Sensor_Analysis_Reconciled.xlsx      <- Script2
      - Duration_Correlation_BlandAltman/          <- Script3
      - Human_Study_Cluster_Bootstrap_CI.xlsx      <- Script4 (pooled AND macro
                                                       Precision/Recall/F1, each
                                                       with percentile + BCa CI)
      - Duration_Distribution_and_Threshold_Sensitivity/  <- Script5 (per-puff
                                                       duration stats/histograms +
                                                       0/0.2/0.4/0.6 s threshold sweep)


How to reproduce every number in the manuscript
------------------------------------------------
1. Install requirements: pip install pandas numpy scipy openpyxl matplotlib
2. From Codes/, run each script, passing the path to Participant Data/
   and a desired output path (see Codes/ReadMe.txt for exact commands).
3. Compare against the reference outputs already in Results/ -- both
   were generated the same way and should match exactly.

Codes/ReadMe.txt also has a one-line lookup table mapping each specific
number/figure in the manuscript to the script that produces it.


Provenance note
----------------
Several earlier scripts were removed from Codes/ after being superseded,
each for a documented reason -- do not reintroduce these approaches:

  - An earlier touch-sensor analysis script independently reimplemented
    device-signal binarization and silently dropped puffs in
    dense-puffing participants (verified bug).
  - Earlier correlation/Bland-Altman scripts used an "all puffs" duration
    definition that doesn't satisfy Bland-Altman's "paired measurement of
    the same event" assumption.
  - A closed-form (Cochran ratio-of-totals) implementation of the pooled
    CI, "Script2_Human_Study_Confidence_Intervals.py", matched the
    professor's originally specified formula exactly (verified against
    live Excel formulas) and is a legitimate, correct method -- it was
    removed only because the manuscript's reported numbers switched to
    the bootstrap/BCa CI throughout (Script4), to match the method your
    bench-testing coauthor used for the bench-lifecycle CIs, so it was no
    longer producing a number that appears in the manuscript. See
    CI_Methods_Description.docx (Manuscript/) for the full closed-form
    derivation if that method needs to be revisited.
  - A separate, pre-consolidation bootstrap script covered only the
    pooled target; it was merged into Script4, which now covers both
    pooled and macro in one place.

See Codes/ReadMe.txt and each current script's header comment for
further detail.
