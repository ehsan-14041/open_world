"""
Ordering policies. Every policy sees only ib.Obs (what the benchmark environment shows before the order),
the training samples, the promised lead time and the two prices.

    OR            replica of the benchmark's own baseline (scripts/run_or.py, policy 'capped')
    Rolling       OR with demand statistics from the most recent W observations
    Cusum         OR with demand statistics from the observations since the last detected change
    SupplyAware   OR with a pipeline that drops overdue orders, an observed lead time and a loss rate
    Rolling+Supply, Cusum+Supply   the two combinations

All constants are fixed in PROTOCOL.md and were set before any of these policies was run.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

Z95 = norm.ppf(0.95)


def _mean_std(xs):                      # the same calls as scripts/run_or.py, so the replica matches to the unit
    return np.mean(xs), (np.std(xs, ddof=1) if len(xs) > 1 else 0)


class OR:
    """Capped base-stock on all history, promised lead time, the environment's in-transit figure."""
    name = "OR"
    CAPPED = True

    def __init__(self, inst):
        self.train, self.L = list(inst.train), inst.promised

    # -- the three pieces the variants replace --------------------------------------------------------
    def samples(self, obs):
        return self.train + obs.demands

    def supply(self, obs):
        """(inventory position, lead time used, loss rate used)."""
        return obs.on_hand + obs.in_transit, self.L, 0.0

    # ---------------------------------------------------------------------------------------------
    def order(self, obs):
        xs = self.samples(obs)
        if not xs:
            return 0
        m, s = _mean_std(xs)
        ip, L, loss = self.supply(obs)
        z = norm.ppf(obs.p / (obs.p + obs.h))
        mu_hat, sigma_hat = (1 + L) * m, np.sqrt(1 + L) * s
        base = mu_hat + z * sigma_hat
        cap = mu_hat / (1 + L) + Z95 * sigma_hat / np.sqrt(1 + L)       # one period's mean + 1.645 sd
        want = max(int(np.ceil(base - ip)), 0)
        if loss > 0:                                    # order more to offset the share that will not arrive
            want = int(math.ceil(want / (1 - loss)))
            cap = cap / (1 - loss)
        return max(min(want, int(np.ceil(cap))), 0) if self.CAPPED else want


class Rolling(OR):
    name = "Rolling"
    W = 10

    def samples(self, obs):
        return (self.train + obs.demands)[-self.W:]


class Cusum(OR):
    """Two-sided tabular CUSUM on standardised demand; on an alarm the estimation window restarts."""
    name = "Cusum"
    K, H, MIN = 0.5, 4.0, 3

    def __init__(self, inst):
        super().__init__(inst)
        self.start, self.seen, self.hi, self.lo = 0, 0, 0.0, 0.0

    def samples(self, obs):
        xs = self.train + obs.demands
        while self.seen < len(xs):                      # feed observations one at a time, in order
            i = self.seen
            seg = xs[self.start:i]
            if len(seg) >= self.MIN:
                m, s = _mean_std(seg)
                if s > 0:
                    zed = (xs[i] - m) / s
                    self.hi = max(0.0, self.hi + zed - self.K)
                    self.lo = max(0.0, self.lo - zed - self.K)
                    if self.hi > self.H or self.lo > self.H:
                        self.start = max(0, i - self.MIN + 1)     # keep the newest MIN observations
                        self.hi = self.lo = 0.0
            self.seen += 1
        return xs[self.start:]


class SupplyAware(OR):
    """
    Uses what the environment reports about arrivals:
      * an order still outstanding more than max(promised, longest lead time seen) periods is treated as lost
        and leaves the inventory position;
      * the lead time is the rounded-up mean of the lead times seen so far (promised until one is seen);
      * the loss rate is lost / (lost + arrived), capped at 0.5.
    """
    name = "SupplyAware"
    MAX_LOSS = 0.5

    def supply(self, obs):
        seen = [a - od for a, _, od in obs.arrivals]
        horizon = max([self.L] + seen)
        arrived = {od for _, _, od in obs.arrivals}
        live = lost = n_lost = n_arrived = 0
        for od, q in enumerate(obs.orders, start=1):
            if q <= 0:
                continue
            if od in arrived:
                n_arrived += 1
            elif obs.t - od > horizon:
                n_lost += 1
            else:
                live += q
        L = int(math.ceil(sum(seen) / len(seen))) if seen else self.L
        loss = min(self.MAX_LOSS, n_lost / (n_lost + n_arrived)) if (n_lost + n_arrived) else 0.0
        return obs.on_hand + live, L, loss


class RollingSupply(SupplyAware):
    name = "Rolling+Supply"
    samples = Rolling.samples
    W = Rolling.W


class CusumSupply(SupplyAware):
    name = "Cusum+Supply"
    K, H, MIN = Cusum.K, Cusum.H, Cusum.MIN
    samples = Cusum.samples

    def __init__(self, inst):
        super().__init__(inst)
        self.start, self.seen, self.hi, self.lo = 0, 0, 0.0, 0.0


BASELINES = [Rolling, Cusum, SupplyAware, RollingSupply, CusumSupply]
PRIMARY = "Cusum+Supply"


def variant(base, label, **consts):
    return type(label, (base,), {"name": label, **consts})


# Declared in PROTOCOL.md as sensitivity runs; never used for the headline numbers.
SENSITIVITY = [
    variant(RollingSupply, "Rolling+Supply W=5", W=5),
    variant(RollingSupply, "Rolling+Supply W=20", W=20),
    variant(CusumSupply, "Cusum+Supply h=3", H=3.0),
    variant(CusumSupply, "Cusum+Supply h=5", H=5.0),
    variant(CusumSupply, "Cusum+Supply uncapped", CAPPED=False),
    variant(OR, "OR uncapped", CAPPED=False),
]
