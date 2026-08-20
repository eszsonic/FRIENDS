"""
Device-cluster bootstrap for FRIENDS lifecycle bench testing.
Resamples ENDS devices with replacement; recomputes pooled metrics each replicate.
Reads FRIENDS-Data-V5-CI-corrected.xlsx directly.
"""
import re, math, numpy as np, openpyxl
from scipy import stats

XLSX = 'C:/Users/Rafi/Box Sync/PhD/Friends/Paper/Professor/data collection/FRIENDS Raw Test DataFRIENDS-Data-V5-CI-corrected.xlsx'
B, SEED = 10000, 12345

def load_devices(path=XLSX):
    """Return one row per device: [TP, FP, FN, |count err|, puffs, |dur err|, dur]."""
    wv = openpyxl.load_workbook(path, data_only=True)
    wf = openpyxl.load_workbook(path, data_only=False)
    ad, dv, df = wv['All Data'], wv['Data Summary'], wf['Data Summary']
    devs, names = [], []
    spans = [(r, re.search(r"!([A-Z]+)(\d+):([A-Z]+)(\d+)", df[f'J{r}'].value))
             for r in range(3, 27)]
    for r, m in spans:
        acc = np.zeros(7)
        for rr in range(int(m.group(2)), int(m.group(4)) + 1):
            d = ad[f'D{rr}'].value
            if d is None:
                continue
            c = ad[f'J{rr}'].value
            prog, meas = ad[f'F{rr}'].value, ad[f'K{rr}'].value
            acc += [min(d, c), max(c - d, 0), max(d - c, 0),
                    abs(c - d), d, abs(meas - prog), prog]
        devs.append(acc); names.append(dv[f'B{r}'].value)
    # Logic Pro and Nord 2 live outside Data Summary; include for the 26-device set
    for rr, nm in ((60, 'Logic Pro'), (45, 'Nord 2')):
        d, c = ad[f'D{rr}'].value, ad[f'J{rr}'].value
        prog, meas = ad[f'F{rr}'].value, ad[f'K{rr}'].value
        devs.append(np.array([min(d, c), max(c - d, 0), max(d - c, 0),
                              abs(c - d), d, abs(meas - prog), prog]))
        names.append(nm)
    return np.array(devs, float), names

def pooled(M):
    tp, fp, fn, ae, x, at, xt = M.sum(0)
    p, r = tp / (tp + fp), tp / (tp + fn)
    return np.array([p, r, 2 * p * r / (p + r), ae / x, at / xt])

def bca(theta_hat, boot, jack):
    """Bias-corrected and accelerated interval."""
    z0 = stats.norm.ppf((boot < theta_hat).mean())
    jm = jack.mean()
    a = ((jm - jack) ** 3).sum() / (6 * (((jm - jack) ** 2).sum()) ** 1.5)
    out = []
    for q in (0.025, 0.975):
        z = stats.norm.ppf(q)
        adj = stats.norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))
        out.append(np.percentile(boot, 100 * adj))
    return out

M, names = load_devices()
n = len(M)
pt = pooled(M)
rng = np.random.default_rng(SEED)
boot = np.array([pooled(M[rng.integers(0, n, n)]) for _ in range(B)])
jack = np.array([pooled(np.delete(M, i, 0)) for i in range(n)])

labels = ['precision', 'recall', 'F1', 'puff-count error', 'duration RE']
print(f"Device-cluster bootstrap: n = {n} devices, B = {B:,}, seed {SEED}\n")
print(f"{'metric':18}{'estimate':>10}{'percentile 95% CI':>26}{'BCa 95% CI':>26}")
for i, lab in enumerate(labels):
    lo, hi = np.percentile(boot[:, i], [2.5, 97.5])
    blo, bhi = bca(pt[i], boot[:, i], jack[:, i])
    k = 1 if lab == 'F1' else 100
    f = '.3f' if lab == 'F1' else '.2f'
    print(f"{lab:18}{pt[i]*k:10{f}}"
          f"{f'[{lo*k:{f}}, {hi*k:{f}}]':>26}"
          f"{f'[{blo*k:{f}}, {bhi*k:{f}}]':>26}")
