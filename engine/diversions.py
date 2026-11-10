"""UAE multi-airport diversion balancer.

Ranks alternates for one diverting flight by: weather at that time vs the airport's
ILS minima, A380 acceptance, flying time, remaining diversion capacity (load is
spread so no airport is overloaded) and ground transfer time back to DXB.
"""
import pandas as pd

from . import config as C


class Balancer:
    def __init__(self, airports: pd.DataFrame, metar: pd.DataFrame):
        self.ap = airports[airports["icao"] != "OMDB"].set_index("icao")
        self.metar = metar.sort_values("valid_local")
        self.used = {i: 0 for i in self.ap.index}

    def _vis(self, icao: str, t) -> float:
        m = self.metar[(self.metar["station"] == icao) & (self.metar["valid_local"] <= t)]
        return float(m["vis_m"].iloc[-1]) if not m.empty and pd.notna(m["vis_m"].iloc[-1]) else 9999.0

    def choose(self, flight, t):
        """Return (icao or None, facts). facts explains every alternate considered."""
        options, rejected = [], {}
        for icao, a in self.ap.iterrows():
            vis = self._vis(icao, t)
            cap = C.ALTERNATE_CAPACITY.get(icao, 5)
            if vis < a["approx_min_rvr_m"]:
                rejected[icao] = f"visibility {int(vis)} m below CAT {a['ils_cat']} minima ({a['approx_min_rvr_m']} m)"
                continue
            if flight["size_class"] == "F" and (
                    a["a380"] == "no" or (a["a380"] == "emirates_only" and flight["airlinecode_iata"] != "EK")):
                rejected[icao] = "does not accept A380 diversions"
                continue
            if self.used[icao] >= cap:
                rejected[icao] = f"diversion capacity full ({cap} aircraft)"
                continue
            fly = a["km_from_main"] / C.CRUISE_KM_PER_MIN + C.DIVERSION_FIXED_MIN
            load = self.used[icao] / cap
            # minutes-equivalent score: flying + passenger transfer + crowding penalty
            score = fly + 0.5 * a["est_transfer_min"] + 60 * load
            options.append((score, icao, fly, vis, load))
        if not options:
            return None, {"rejected": rejected}
        score, icao, fly, vis, load = min(options)
        self.used[icao] += 1
        a = self.ap.loc[icao]
        return icao, {
            "divert_to": icao, "fly_min": round(fly), "visibility_m": int(vis),
            "ils_cat": a["ils_cat"], "transfer_min_to_dxb": int(a["est_transfer_min"]),
            "alternate_load_pct": round(100 * load),
            "alternatives_ranked": [o[1] for o in sorted(options)],
            "rejected": rejected,
        }
