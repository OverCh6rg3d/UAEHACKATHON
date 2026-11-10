"""Stand allocation with hard compatibility and no-overlap constraints."""
import math

import pandas as pd

from . import config as C

RANK = {"C": 0, "D": 1, "E": 2, "F": 3}


def fits(stand_class: str, aircraft_class: str) -> bool:
    """A stand fits an aircraft of its own size class or smaller. Unknown stands take Code C."""
    s = RANK.get(stand_class, 0)
    a = RANK.get(aircraft_class, 2)  # unknown aircraft treated as Code E (cautious)
    return s >= a


def _km(a, b) -> float:
    if pd.isna(a.lat) or pd.isna(b.lat):
        return 99.0
    p = math.pi / 180
    x = (b.lon - a.lon) * p * math.cos((a.lat + b.lat) * p / 2)
    return 6371 * math.hypot(x, (b.lat - a.lat) * p)


class StandBoard:
    """Tracks which stand is busy when; refuses any overlap."""

    def __init__(self, stands: pd.DataFrame, parked: pd.DataFrame, horizon_end):
        self.stands = stands.set_index("stand")
        self.busy = {s: [] for s in self.stands.index}
        for r in parked.itertuples():
            if r.stand in self.busy:
                end = r.off_block if pd.notna(r.off_block) else horizon_end
                self.busy[r.stand].append((r.actualinblocktime, end))

    def free(self, stand, t0, t1) -> bool:
        return all(t1 <= a or t0 >= b for a, b in self.busy[stand])

    def keep_original(self, flight, t_in, t_out):
        """Pass 1: give the flight its own stand if it fits and is free. Returns stand or None."""
        orig, cls = flight["stand"], flight["size_class"]
        if orig not in self.busy:
            # stand not on the GCAA charts (e.g. remote S44x): not modelled, keep as recorded
            return orig if isinstance(orig, str) else None
        if fits(self.stands.loc[orig, "size_class"], cls) and self.free(orig, t_in, t_out):
            self.busy[orig].append((t_in, t_out))
            return orig
        return None

    def assign(self, flight, t_in, t_out):
        """Pass 2: nearest fitting free stand (same apron first), else remote."""
        orig = flight["stand"]
        cls = flight["size_class"]
        ref = self.stands.loc[orig] if orig in self.stands.index else None
        cands = []
        for s, row in self.stands.iterrows():
            if s == orig or not fits(row["size_class"], cls) or not self.free(s, t_in, t_out):
                continue
            same_apron = ref is not None and row["apron"] == ref["apron"]
            dist = _km(ref, row) if ref is not None else 99.0
            cands.append((0 if same_apron else 1, dist, s))
        if not cands:
            return C.REMOTE_STAND, {"kept_original": False, "why": "no fitting contact stand free"}
        _, dist, s = min(cands)
        self.busy[s].append((t_in, t_out))
        why = ("original stand still occupied" if orig in self.busy and not self.free(orig, t_in, t_out)
               else "original stand does not fit or is unknown")
        return s, {"kept_original": False, "why": why, "km_from_original": round(dist, 2),
                   "stand_class": self.stands.loc[s, "size_class"]}


def count_conflicts(intervals: pd.DataFrame) -> int:
    """Pairs of aircraft whose stand times overlap (for the 'as it happened' plan)."""
    n = 0
    for _, g in intervals.dropna(subset=["stand", "t_in", "t_out"]).groupby("stand"):
        g = g.sort_values("t_in")
        prev_end = None
        for r in g.itertuples():
            if prev_end is not None and r.t_in < prev_end:
                n += 1
            prev_end = r.t_out if prev_end is None else max(prev_end, r.t_out)
    return n
