# FRIENDS

Firmware, hardware design, and data-analysis code for the FRIENDS v1 e-cigarette puffing monitor, supporting the manuscript submitted to *IEEE Transactions on Instrumentation and Measurement*.

---

## Repository layout

```
FRIENDS/
├── main.c              # MSP430G2433 firmware (puff / touch / thermistor logging)
├── lighter.h           # Pin definitions, UART helpers, bit-bang SPI macros
├── flash.h / flash.c   # SPI driver for 4 Mbit serial flash (SST25VF040B)
├── targetConfigs/      # Code Composer Studio target-configuration (.ccxml) file
├── HARDWARE/
│   └── V1/             # Schematic, PCB, and BOM (released upon manuscript acceptance)
└── IEEE TIM data/
    ├── HUMAN LAB VALIDATION/   # Human lab study (22 participants)
    ├── DAILY CARRY/            # Daily-carry field study (GeekBar & NJOY devices)
    └── LIFECYCLE VALIDATION/   # Long-term device lifecycle testing
```

---

## Firmware

| File | Description |
|------|-------------|
| `main.c` | Top-level firmware for the **MSP430G2433** microcontroller. Detects puff events via an RF-envelope sensor on P2.0, touch events on P2.1, and optional thermistor readings (ADC10). Each event is timestamped with a 64-bit fixed-point counter (UNIX seconds \|\| Timer\_A ticks) and written to serial flash over bit-bang SPI. A half-duplex software UART (8 MHz / 115 200 baud) is used to read back or set the RTC. |
| `lighter.h` | Pin assignments (`SENSOR`, `TOUCH`, `LED`, `THERMISTOR_ON_OFF`), UART timing constants, `ENABLE_SENSORS` / `DISABLE_SENSORS` macros, and declarations for UART and integer-conversion helpers. |
| `flash.h` / `flash.c` | Bit-bang SPI driver for the 4 Mbit (512 KB) serial flash. Exposes page-write, sector/block/chip erase, status-read, and deep-power-down commands. |

**Toolchain:** Texas Instruments Code Composer Studio v5, MSP430-GCC.

---

## Hardware

`HARDWARE/V1/` will contain the schematic, PCB layout, and bill of materials for the FRIENDS v1 device upon acceptance of the manuscript for publication.

---

## IEEE TIM data

### Human Lab Validation (`IEEE TIM data/HUMAN LAB VALIDATION/`)

22-participant controlled laboratory study. Video-coded puff events (25 fps camera) are compared against FRIENDS device detections.

**`Codes/` — analysis pipeline (run from the `Codes/` directory, zero arguments required):**

| Script | Purpose | Output |
|--------|---------|--------|
| `Script1_0.4sec_threshold_performance_metrics.py` | Confusion matrix (TP/FN/FP) at the 0.4 s production threshold; pooled and macro Precision/Recall/F1 with 95 % BCa bootstrap CIs (B = 10 000, seed = 12345). | `Results/Reconciled_Detection_Metrics_Summary.xlsx` |
| `Script2_different_threshold_sensitivity_analysis.py` | Sweeps thresholds (0.0, 0.2, 0.4, 0.6 s); reuses Script 1 unmodified. | `Results/Threshold_Sensitivity_Performance_Metrics/` |
| `Script3_Touch_Sensor_Analysis.py` | Touch-sensor gating: restricts detection to FRIENDS puffs that overlap a touch activation. | `Results/Touch_Sensor_Analysis.xlsx` |
| `Script4_Duration_Correlation_BlandAltman.py` | Pearson correlation + Bland-Altman analysis of participant-level mean puff duration (camera vs. FRIENDS). | `Results/Duration_Correlation_BlandAltman/` |
| `Script5_Puff_Duration_Distribution.py` | Pooled individual-puff duration distributions and histograms. | `Results/Puff_Duration_Distribution/` |

Scripts 2–5 import Script 1 directly so all numbers are reproducible from raw `Participant Data/` alone — no intermediate spreadsheet is consumed.

**Key verified results (0.4 s threshold, 22 participants):**
- Pooled: TP = 799, FN = 67, FP = 73 (866 true puffs)
  - Precision = 0.9163 [0.8072, 0.9635]
  - Recall = 0.9226 [0.8153, 0.9756]
  - F1 = 0.9194 [0.8414, 0.9597]
- Macro: Precision = 0.9337, Recall = 0.9242, F1 = 0.9205

**`Participant Data/`** — per-participant subdirectories (`FRIENDS20xx/`) each containing:
- `DEVICE_DATA/` — raw FRIENDS device event log (converted with durations)
- `VIDEO_DATA/` — video-coded puff event log
- `OUTPUT_DIR/` — signal-alignment plots and per-participant analysis spreadsheets
- `OUTPUT_TOUCH_DIR/` — touch-sensor overlay plots and analysis

### Daily Carry (`IEEE TIM data/DAILY CARRY/`)

Field study using two commercial e-cigarette models (**GeekBar**, **NJOY**) over 5 days each. Contains:
- `Raw data/GeekBar/` and `Raw data/NJOY/` — raw and converted/duration-annotated device logs
- `LOO_CV_v3.py` — leave-one-day-out cross-validation with pooled ratio metrics and cluster-robust 95 % CIs
- `combined_plot_v2.py` — combined visualisation
- `Book1.xlsx` — summary data

### Lifecycle Validation (`IEEE TIM data/LIFECYCLE VALIDATION/`)

Long-term device reliability testing. Contains:
- `Lifecycle-testing-FRIENDS-Data-V5.xlsx` — raw lifecycle data
- `compute_aggregate_performance.py` — aggregate performance metrics
- `plot_duration_error_by_device.py` — duration-error plots by device
- `requirements.txt` — Python dependencies

**Usage:**
```bash
python compute_aggregate_performance.py
python plot_duration_error_by_device.py Lifecycle-testing-FRIENDS-Data-V5.xlsx --output mean_puff_duration_error_by_device.png
```
