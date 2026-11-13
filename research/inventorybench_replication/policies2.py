"""
Second-step supply rule (PROTOCOL_V2.md). The demand side is the first step's CUSUM rule, unchanged.

Supply2 is a family; `design.py` explores it on the design half and FROZEN below names the one member that is
run on the test half. policies.py is not modified.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

from policies import Z95, CusumSupply, _mean_std


class Supply2(CusumSupply):
    name = "Cusum+Supply2"
    PIPE = "hard"        # "hard": an order counts in full until it is overdue; "expected": weighted by its chance of still arriving
    LEAD = "mean"        # protection interval from the "mean" (rounded up) or the "max" of the lead times seen
    INFLATE = True       # divide the order by (1 - loss rate)
    CAPM = 1.0           # cap = CAPM x (one period's mean + 1.645 sd) / (1 - loss rate); None = no cap
    KAPPA = 0.0          # extra stock of KAPPA x loss rate x (1 + L) x mean demand
    HORIZON = "max"      # an order is overdue after max(promised, "max" | "mean" of the lead times seen) periods
    MAX_LOSS = 0.5

    def supply(self, obs):
        seen = [a - od for a, _, od in obs.arrivals]
        horizon = max([self.L] + seen) if self.HORIZON == "max" or not seen else max(self.L, int(math.ceil(sum(seen) / len(seen))))
        arrived = {od for _, _, od in obs.arrivals}
        outstanding, n_lost = [], 0
        for od, q in enumerate(obs.orders, start=1):
            if q <= 0 or od in arrived:
                continue
            if obs.t - od > horizon:
                n_lost += 1
            else:
                outstanding.append((obs.t - od, q))
        n_arr = len(seen)
        loss = min(self.MAX_LOSS, n_lost / (n_lost + n_arr)) if (n_lost + n_arr) else 0.0
        if self.PIPE == "hard" or not seen:
            live = sum(q for _, q in outstanding)
        else:
            live = 0.0
            for age, q in outstanding:                       # not arrived by age - 1, so its lead time is >= age or it is lost
                later = sum(1 for s in seen if s >= age) / n_arr * (1 - loss)
                live += q * (later / (later + loss) if later + loss > 0 else 0.0)
        if not seen:
            L = self.L
        elif self.LEAD == "max":
            L = max(seen)
        else:
            L = int(math.ceil(sum(seen) / n_arr))
        return obs.on_hand + live, L, loss

    def order(self, obs):
        xs = self.samples(obs)
        if not xs:
            return 0
        m, s = _mean_std(xs)
        ip, L, loss = self.supply(obs)
        z = norm.ppf(obs.p / (obs.p + obs.h))
        base = (1 + L) * m + z * np.sqrt(1 + L) * s + self.KAPPA * loss * (1 + L) * m
        want = max(base - ip, 0.0)
        if self.INFLATE and loss > 0:
            want = want / (1 - loss)
        want = int(np.ceil(want))
        if self.CAPM is None:
            return want
        cap = self.CAPM * (m + Z95 * s) / ((1 - loss) if self.INFLATE else 1.0)
        return max(min(want, int(np.ceil(cap))), 0)


def member(**consts):
    label = "S2[" + ",".join(f"{k}={v}" for k, v in sorted(consts.items())) + "]"
    return type(label, (Supply2,), {"name": label, **consts})


# Filled in after the design half and before the test half (see PROTOCOL_V2.md).
FROZEN = type("Cusum+Supply2", (Supply2,), {"name": "Cusum+Supply2", "PIPE": "hard", "LEAD": "mean", "INFLATE": False,
                                           "CAPM": 0.8, "KAPPA": -0.5, "HORIZON": "mean"})
