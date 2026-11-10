"""Fog prediction model: will fog start at this airport in the next 1-3 hours?

Trained only on METAR reports for the seven UAE airports (the same source as
script 01), so it needs nothing that is not open data.

    python 07_fog_model.py --download     # once: fetch the METAR history (2014 ->)
    python 07_fog_model.py                # features, train, evaluate, alert timelines

Design
  Rows     every METAR report where there is no fog right now
  Target   fog (FG code or visibility < 1000 m) reported within the next 3 hours
  Features current visibility, temperature, dew point, spread, humidity, wind,
           their change over the last 1 and 3 hours, mist/haze codes, time of day,
           season, hours since sunset, fog earlier today / yesterday, and whether
           fog is already reported at the other UAE airports
  Model    gradient-boosted trees (scikit-learn HistGradientBoostingClassifier)
  Split    by time, never random: train < 2024, tune threshold on 2024,
           test 2025 -> today (includes the replay days, which the model never saw)

Outputs in processed/fog_model/:
  model.joblib, metrics.json, feature_importance.csv, test_events.csv
and processed/scenario_<date>/alert_timeline.csv for every scenario folder, with
the state at each report: CLEAR, WATCH (fog likely within hours), WARNING (fog
imminent) or ALERT (fog observed).
"""
import argparse
import importlib
import json

import numpy as np
import pandas as pd

from common import MAIN_AIRPORT, PROCESSED, RAW_METAR, UAE_AIRPORTS

metar01 = importlib.import_module("01_weather_metar")

HIST = RAW_METAR / "history"
OUT = PROCESSED / "fog_model"
HORIZON_H = 3
TRAIN_END, VALID_END = "2024-01-01", "2025-01-01"
WATCH_FAR_TARGET = 0.5   # WARNING level: at most half of report-level warnings are false
WATCH_EVENT_TARGET = 0.9  # WATCH level: warn at least this share of fog events


def download(start_year: int):
    HIST.mkdir(parents=True, exist_ok=True)
    end = pd.Timestamp.now(tz="UTC").normalize() + pd.Timedelta(days=1)
    for st in UAE_AIRPORTS:
        if (HIST / f"{st}.csv").exists():     # resumable: delete the file to re-download
            print(f"{st}: already downloaded, skipping", flush=True)
            continue
        parts = []
        for y in range(start_year, end.year + 1):
            a, b = pd.Timestamp(y, 1, 1), min(pd.Timestamp(y + 1, 1, 1), end.tz_localize(None))
            parts.append(metar01.download(st, a, b))
            print(f"  {st} {y}: {len(parts[-1])} reports", flush=True)
        df = pd.concat(parts, ignore_index=True)
        df.to_csv(HIST / f"{st}.csv", index=False)
        print(f"{st}: {len(df)} reports saved", flush=True)


def load_history() -> pd.DataFrame:
    files = sorted(HIST.glob("*.csv"))
    if not files:
        raise SystemExit("No history. Run: python 07_fog_model.py --download")
    df = metar01.clean(pd.concat((pd.read_csv(f, low_memory=False) for f in files), ignore_index=True))
    df = df.drop_duplicates(["station", "valid_utc"]).dropna(subset=["vis_m"])
    for c in ["relh", "drct", "sknt"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["station", "valid_utc"]).reset_index(drop=True)


def _past(g: pd.DataFrame, col: str, hours: float) -> pd.Series:
    """Value of `col` about `hours` ago at the same station (latest report at or before)."""
    left = pd.DataFrame({"t": g["valid_utc"] - pd.Timedelta(hours=hours)})
    right = g[["valid_utc", col]].rename(columns={"valid_utc": "t"})
    return pd.merge_asof(left, right, on="t", tolerance=pd.Timedelta(hours=1.5))[col].set_axis(g.index)


def features(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for st, g in df.groupby("station", sort=False):
        g = g.copy()
        t = g["valid_utc"]
        fog = g["is_fog"].astype(int)
        # target: any fog report in (t, t + 3 h]
        tv = t.values.astype("datetime64[s]").astype("int64")
        csum = np.concatenate([[0], np.cumsum(fog.values)])
        hi = np.searchsorted(tv, tv + HORIZON_H * 3600, side="right")
        lo = np.arange(len(tv)) + 1
        g["y"] = ((csum[hi] - csum[lo]) > 0).astype(int)
        # complete label only if we have data covering the horizon
        g["label_ok"] = (tv[np.minimum(hi, len(tv) - 1)] - tv) >= 2 * 3600
        wx = g["wxcodes"].fillna("").astype(str)
        g["mist"] = wx.str.contains(r"\bBR\b").astype(int)
        g["haze_dust"] = wx.str.contains(r"HZ|DU|SA").astype(int)
        g["shallow_fog"] = wx.str.contains(r"BCFG|MIFG|PRFG|VCFG").astype(int)
        for col in ["vis_m", "spread_c", "temp_c", "sknt", "relh"]:
            for h in (1, 3):
                g[f"{col}_d{h}h"] = g[col] - _past(g, col, h)
        rad = np.deg2rad(g["drct"].fillna(0))
        g["wind_u"] = -g["sknt"].fillna(0) * np.sin(rad)
        g["wind_v"] = -g["sknt"].fillna(0) * np.cos(rad)
        g["calm"] = (g["sknt"].fillna(0) <= 3).astype(int)
        hour = g["valid_local"].dt.hour + g["valid_local"].dt.minute / 60
        g["hour_sin"], g["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
        doy = g["valid_local"].dt.dayofyear
        g["doy_sin"], g["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
        g["night_hours"] = ((hour - 18) % 24).where((hour >= 18) | (hour <= 8), 0)  # hours since ~sunset
        # fog in the previous 24 h at this station (persistence of the weather pattern)
        lo24 = np.searchsorted(tv, tv - 24 * 3600, side="left")
        g["fog_reports_24h"] = csum[np.arange(len(tv))] - csum[lo24]
        out.append(g)
    f = pd.concat(out)
    # network signal: how many OTHER UAE airports report fog in the last hour
    f["hour_bin"] = f["valid_utc"].dt.floor("h")
    own = f.groupby(["hour_bin", "station"])["is_fog"].max().astype(int).rename("own").reset_index()
    own["hour_bin"] += pd.Timedelta(hours=1)          # previous full hour: no look-ahead
    tot = own.groupby("hour_bin")["own"].sum().rename("tot").reset_index()
    f = f.merge(own, on=["hour_bin", "station"], how="left").merge(tot, on="hour_bin", how="left")
    f["fog_elsewhere_prev_h"] = f["tot"].fillna(0) - f["own"].fillna(0)
    f = f.drop(columns=["own", "tot"])
    f["station_code"] = f["station"].astype("category").cat.codes
    return f


FEATS = ["vis_m", "temp_c", "dew_c", "spread_c", "relh", "sknt", "wind_u", "wind_v", "calm",
         "mist", "haze_dust", "shallow_fog",
         "vis_m_d1h", "vis_m_d3h", "spread_c_d1h", "spread_c_d3h", "temp_c_d1h", "temp_c_d3h",
         "sknt_d1h", "sknt_d3h", "relh_d1h", "relh_d3h",
         "hour_sin", "hour_cos", "doy_sin", "doy_cos", "night_hours",
         "fog_reports_24h", "fog_elsewhere_prev_h", "station_code"]


def scores(y, p, thr) -> dict:
    pred = p >= thr
    tp, fp, fn = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum())
    return {"threshold": round(float(thr), 3), "hits": tp, "false_alarms": fp, "misses": fn,
            "pod": round(tp / max(1, tp + fn), 3), "far": round(fp / max(1, tp + fp), 3),
            "csi": round(tp / max(1, tp + fp + fn), 3)}


def events(test: pd.DataFrame, thr: float) -> pd.DataFrame:
    """Per fog event in the test period: was there a Watch before onset, and how early?"""
    rows = []
    for st, g in test.groupby("station"):
        g = g.sort_values("valid_utc")
        fog = g["is_fog"].values
        onset = np.where(fog & ~np.r_[False, fog[:-1]])[0]
        last_end = None
        for i in onset:
            t_on = g["valid_utc"].iloc[i]
            if last_end is not None and (t_on - last_end) < pd.Timedelta(hours=6):
                last_end = t_on
                continue  # same event (fog thinning and returning)
            last_end = t_on
            w = g[(g["valid_utc"] >= t_on - pd.Timedelta(hours=6)) & (g["valid_utc"] < t_on) & ~g["is_fog"]]
            above = (w["p"] >= thr).values
            recent = (w["valid_utc"] >= t_on - pd.Timedelta(hours=HORIZON_H)).values
            warned = bool((above & recent).any())
            # lead = start of the unbroken run of warnings that contains the last one before onset
            lead = None
            if warned:
                j = np.where(above & recent)[0].max()
                while j > 0 and above[j - 1]:
                    j -= 1
                lead = (t_on - w["valid_utc"].iloc[j]).total_seconds() / 60
            rows.append({"station": st, "onset_local": g["valid_local"].iloc[i], "warned": warned,
                         "lead_min": lead, "min_vis_m": g["vis_m"].iloc[i:i + 12].min()})
    return pd.DataFrame(rows)


def tier_stats(part: pd.DataFrame, thr: float) -> dict:
    """Event-level skill of one alert level, plus how often it fires at the main airport."""
    ev = events(part, thr)
    g = part[part["station"] == MAIN_AIRPORT].sort_values("valid_utc")
    above = (g["p"] >= thr).fillna(False).values
    t, fog = g["valid_utc"].values, g["is_fog"].values
    episodes = false = 0
    last = None
    for i in np.where(above & ~np.r_[False, above[:-1]])[0]:
        if last is not None and (t[i] - last) < np.timedelta64(6, "h"):
            continue                      # same episode
        last = t[i]
        episodes += 1
        false += not fog[(t >= t[i]) & (t <= t[i] + np.timedelta64(6, "h"))].any()
    years = max(1e-9, (part["valid_utc"].max() - part["valid_utc"].min()).days / 365.25)
    d = ev[ev["station"] == MAIN_AIRPORT]
    lead = ev["lead_min"].dropna()
    return {"threshold": round(float(thr), 3),
            "events": len(ev), "events_warned": int(ev["warned"].sum()),
            "pct_events_warned": round(100 * ev["warned"].mean(), 1) if len(ev) else None,
            "median_lead_min": None if lead.empty else float(lead.median()),
            f"{MAIN_AIRPORT}_events": len(d), f"{MAIN_AIRPORT}_warned": int(d["warned"].sum()),
            f"{MAIN_AIRPORT}_lead_min": [None if pd.isna(x) else int(x) for x in d["lead_min"]],
            f"{MAIN_AIRPORT}_episodes_per_year": round(episodes / years, 1),
            f"{MAIN_AIRPORT}_false_episodes_per_year": round(false / years, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--start-year", type=int, default=2014)
    a = ap.parse_args()
    if a.download:
        download(a.start_year)
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import average_precision_score, roc_auc_score
    import joblib

    OUT.mkdir(exist_ok=True)
    df = features(load_history())
    data = df[(~df["is_fog"]) & df["label_ok"]].copy()   # predict ONSET: only rows with no fog now
    tr = data[data["valid_utc"] < TRAIN_END]
    va = data[(data["valid_utc"] >= TRAIN_END) & (data["valid_utc"] < VALID_END)]
    te = data[data["valid_utc"] >= VALID_END]
    print(f"rows train {len(tr)}, valid {len(va)}, test {len(te)}; "
          f"positives {tr.y.mean():.2%} / {va.y.mean():.2%} / {te.y.mean():.2%}")

    model = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                           l2_regularization=1.0, class_weight="balanced",
                                           categorical_features=[FEATS.index("station_code")],
                                           early_stopping=True, validation_fraction=0.1, random_state=42)
    model.fit(tr[FEATS], tr["y"])
    pv, pt = model.predict_proba(va[FEATS])[:, 1], model.predict_proba(te[FEATS])[:, 1]

    # Watch threshold: best POD on the validation year with FAR <= target
    cands = np.quantile(pv, np.linspace(0.90, 0.9995, 200))
    ok = [(scores(va["y"].values, pv, t), t) for t in cands]
    ok = [(s, t) for s, t in ok if s["far"] <= WATCH_FAR_TARGET] or ok[-1:]
    thr = max(ok, key=lambda x: x[0]["pod"])[1]

    # simple rule a forecaster might use, for comparison
    rule = ((te["spread_c"] <= 1.5) & (te["sknt"].fillna(0) <= 5) &
            ((te["valid_local"].dt.hour >= 22) | (te["valid_local"].dt.hour <= 8))).values.astype(float)

    df["p"] = np.nan
    df.loc[~df["is_fog"], "p"] = model.predict_proba(df.loc[~df["is_fog"], FEATS])[:, 1]
    valid_all = df[(df["valid_utc"] >= TRAIN_END) & (df["valid_utc"] < VALID_END)]
    test_all = df[df["valid_utc"] >= VALID_END]
    # Two alert levels.
    #   WARNING = thr: strict, few false alarms, short notice.
    #   WATCH   = the highest threshold that still warns >= 90% of fog events in the
    #             validation year: sensitive, hours of notice, more false watches.
    watch_thr = thr
    for c in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]:
        e = events(valid_all, c)
        if len(e) and e["warned"].mean() >= WATCH_EVENT_TARGET:
            watch_thr = c
    ev = events(test_all, watch_thr)
    ev.to_csv(OUT / "test_events.csv", index=False)
    dxb = ev[ev["station"] == MAIN_AIRPORT]

    metrics = {
        "target": f"fog onset within {HORIZON_H} h (FG code or visibility < 1000 m), rows with no fog now",
        "model": "HistGradientBoostingClassifier (scikit-learn), METAR features only",
        "stations": UAE_AIRPORTS,
        "history": [str(df["valid_utc"].min().date()), str(df["valid_utc"].max().date())],
        "split": {"train": f"< {TRAIN_END}", "validation": f"{TRAIN_END} to {VALID_END}", "test": f">= {VALID_END}"},
        "rows": {"train": len(tr), "validation": len(va), "test": len(te)},
        "positive_rate_test": round(float(te["y"].mean()), 4),
        "test_report_level": {**scores(te["y"].values, pt, thr),
                              "roc_auc": round(float(roc_auc_score(te["y"], pt)), 3),
                              "pr_auc": round(float(average_precision_score(te["y"], pt)), 3)},
        "test_simple_rule": {**scores(te["y"].values, rule, 0.5),
                             "rule": "spread <= 1.5 C and wind <= 5 kt at night"},
        "levels": {
            "WATCH": {"meaning": "fog likely within hours: prepare plans, nothing is sent",
                      "chosen_on": f"validation year: highest threshold warning >= {WATCH_EVENT_TARGET:.0%} of fog events",
                      "validation": tier_stats(valid_all, watch_thr), "test": tier_stats(test_all, watch_thr)},
            "WARNING": {"meaning": "fog imminent: high confidence",
                        "chosen_on": f"validation year: best detection with false-alarm ratio <= {WATCH_FAR_TARGET}",
                        "validation": tier_stats(valid_all, thr), "test": tier_stats(test_all, thr)},
        },
        "watch_threshold": float(watch_thr), "warning_threshold": round(float(thr), 4),
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    joblib.dump({"model": model, "features": FEATS, "watch_threshold": float(watch_thr),
                 "warning_threshold": float(thr)}, OUT / "model.joblib")

    sub = te.sample(min(len(te), 40000), random_state=42)
    imp = permutation_importance(model, sub[FEATS], sub["y"], scoring="average_precision",
                                 n_repeats=3, random_state=42)
    fi = pd.DataFrame({"feature": FEATS, "importance": imp.importances_mean}).sort_values(
        "importance", ascending=False)
    fi.to_csv(OUT / "feature_importance.csv", index=False)

    # alert timeline for each scenario day at the main airport
    m = df[df["station"] == MAIN_AIRPORT]
    for d in sorted(PROCESSED.glob("scenario_*")):
        day = pd.Timestamp(d.name.split("_")[1]).date()
        t = m[(m["valid_local"].dt.date == day) |
              (m["valid_local"].dt.date == day - pd.Timedelta(days=1))].copy()
        t = t[t["valid_local"] >= pd.Timestamp(day, tz="Asia/Dubai") - pd.Timedelta(hours=6)]
        t["state"] = np.where(t["is_fog"], "ALERT", np.where(t["p"] >= thr, "WARNING",
                              np.where(t["p"] >= watch_thr, "WATCH", "CLEAR")))
        t[["valid_local", "vis_m", "spread_c", "sknt", "wxcodes", "p", "state"]].rename(
            columns={"p": "fog_probability_3h"}).to_csv(d / "alert_timeline.csv", index=False)

    print(json.dumps(metrics, indent=2))
    print("\nTop features:\n", fi.head(10).to_string(index=False))
    print("\nDXB test events:\n", dxb.to_string(index=False))


if __name__ == "__main__":
    main()
