"""Day 10: LSTM (PyTorch). One network predicts the 24 h change of 4 metrics
from the last 48 hours of observations, with the same folds, 24 h gap and lambda
shrinkage as every other model.

  python -m src.training.day10_lstm quick     # 1 seed, 8 epochs (smoke test)
  python -m src.training.day10_lstm           # 3 seeds, up to 30 epochs
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.training.data import REG, folds, load

METRICS = ["aqi", "temp_c", "humidity", "wind_speed_ms"]
SEQ_COLS = ["aqi", "pm2_5", "pm10", "o3", "no2", "temp_c", "humidity", "precip_mm",
            "uv_index", "wind_speed_ms", "wind_sin", "wind_cos", "pressure_hpa",
            "cloud_pct", "hour_sin", "hour_cos"]
QUICK = "quick" in sys.argv
L = 48                       # hours of history the LSTM sees
HIDDEN = 32
EPOCHS = 8 if QUICK else 30
PATIENCE = 4
BATCH = 128
LR = 1e-3
SEEDS = [0] if QUICK else [0, 1, 2]
GAP = 24
LAMBDAS = [0.0, 0.25, 0.5, 0.75, 1.0]
Path("docs/results").mkdir(parents=True, exist_ok=True)


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def build_windows(F, fit_rows):
    """Scale with training statistics only, then cut sliding windows of L hours.
    W[k] holds rows k .. k+L-1, so the window ending at row i is W[i - (L - 1)]."""
    mu = F.iloc[fit_rows].mean()
    sd = F.iloc[fit_rows].std().replace(0, 1) + 1e-8
    A = ((F - mu) / sd).clip(-6, 6).to_numpy(np.float32)
    W = np.lib.stride_tricks.sliding_window_view(A, L, axis=0).transpose(0, 2, 1)
    return np.ascontiguousarray(W)


def train_predict(Xfit, Yfit, Xes, Yes, Xva):
    """Train one small LSTM per seed with early stopping; return the average
    prediction for Xva, the epochs used and the best early-stopping losses."""
    import torch
    from torch import nn

    class Net(nn.Module):
        def __init__(self, n_in, n_out):
            super().__init__()
            self.lstm = nn.LSTM(n_in, HIDDEN, batch_first=True)
            self.drop = nn.Dropout(0.2)
            self.out = nn.Linear(HIDDEN, n_out)

        def forward(self, x):
            h, _ = self.lstm(x)
            return self.out(self.drop(h[:, -1]))

    xf, yf = torch.from_numpy(Xfit), torch.from_numpy(Yfit)
    xe, ye = torch.from_numpy(Xes), torch.from_numpy(Yes)
    xv = torch.from_numpy(Xva)
    loss_fn = nn.MSELoss()
    preds, epochs_used, best_losses = [], [], []

    for seed in SEEDS:
        torch.manual_seed(seed)
        net = Net(xf.shape[2], yf.shape[1])
        opt = torch.optim.Adam(net.parameters(), lr=LR, weight_decay=1e-4)
        best, best_state, bad = float("inf"), None, 0
        for ep in range(1, EPOCHS + 1):
            net.train()
            perm = torch.randperm(len(xf))
            for i in range(0, len(xf), BATCH):
                idx = perm[i:i + BATCH]
                opt.zero_grad()
                loss_fn(net(xf[idx]), yf[idx]).backward()
                nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                opt.step()
            net.eval()
            with torch.no_grad():
                v = loss_fn(net(xe), ye).item()
            if v < best - 1e-4:
                best, bad = v, 0
                best_state = {k: t.clone() for k, t in net.state_dict().items()}
            else:
                bad += 1
                if bad >= PATIENCE:
                    break
        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()
        with torch.no_grad():
            preds.append(net(xv).numpy())
        epochs_used.append(ep)
        best_losses.append(best)
    return np.mean(preds, axis=0), epochs_used, best_losses


def main():
    labeled, _, _ = load()
    F = labeled[SEQ_COLS].astype("float64").copy()
    F["precip_mm"] = np.log1p(F["precip_mm"])                # heavy-tailed -> log scale
    now = {m: labeled[REG[m][1]].to_numpy() for m in METRICS}
    y = {m: labeled[REG[m][0]].to_numpy() for m in METRICS}
    CH = np.column_stack([y[m] - now[m] for m in METRICS])   # 24 h change, shape (N, 4)

    splits = folds(len(labeled))
    rows, t0 = [], time.time()
    for k, (tr, va) in enumerate(splits, 1):
        n_es = max(int(0.1 * len(tr)), 300)
        es = tr[-n_es:]                                       # early-stopping slice (latest training rows)
        fit = tr[:-(n_es + GAP)]                              # gap so fit targets never overlap it
        fit = fit[fit >= L - 1]

        W = build_windows(F, fit)
        take = lambda r: W[r - (L - 1)]
        sc = CH[fit].std(axis=0)                              # scale only, no mean: 0 = "no change"
        Ys = (CH / sc).astype(np.float32)

        pred_s, ep, best = train_predict(take(fit), Ys[fit], take(es), Ys[es], take(va))
        dp = pred_s * sc                                      # predicted change, original units

        for j, m in enumerate(METRICS):
            naive = rmse(y[m][va], now[m][va])
            for lam in LAMBDAS:
                p = now[m][va] + lam * dp[:, j]
                rows.append(dict(metric=m, fold=k, model="lstm", lam=lam,
                                 rmse=rmse(y[m][va], p), naive=naive,
                                 bias=float(np.mean(p - y[m][va]))))
            print(f"  {m:14s} full model {rmse(y[m][va], now[m][va] + dp[:, j]):.3f} vs naive {naive:.3f}")
        base_es = float(np.mean(Ys[es] ** 2))         
        print(f"fold {k}: fit {len(fit)} rows | epochs run {ep} | early-stop loss "
              f"{np.round(best, 3)} vs 'no change' {base_es:.3f} "
              f"| {(time.time() - t0) / 60:.1f} min")

    res = pd.DataFrame(rows)
    out = "docs/results/day10_lstm_quick.csv" if QUICK else "docs/results/day10_lstm.csv"
    res.to_csv(out, index=False)
    print(f"\n=== LSTM mean RMSE over folds (lam=0 is the naive baseline) -> {out} ===")
    print(res.pivot_table(index="metric", columns="lam", values="rmse").round(3).to_string())


if __name__ == "__main__":
    main()