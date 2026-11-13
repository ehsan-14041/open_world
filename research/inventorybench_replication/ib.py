"""
Shared code for the InventoryBench replication: instance loading, a simulator that follows the
benchmark's own environment (vendor/InventoryBench/or_agent/envs/VendingMachine/env.py), and scoring.

Nothing here calls a language model or the network.
"""
from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor" / "InventoryBench"
BENCH = VENDOR / "benchmark"
PINNED_SHA = "62b1f1162f19a41d428d47c6cd4ca431f098f6f3"
PROMISED = {"lead_time_0": 0, "lead_time_4": 4, "lead_time_stochastic": 2}   # benchmark_all_strategies.py
INF = float("inf")


@dataclass
class Instance:
    rel: str                 # e.g. synthetic_trajectory/lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_med
    kind: str                # "synthetic" | "real"
    lead_setting: str        # lead_time_0 | lead_time_4 | lead_time_stochastic
    family: str              # demand pattern (synthetic) or "real"
    cluster: str             # instances sharing one demand trajectory source
    promised: int
    item: str
    demand: list[int]
    lead: list[float]        # actual lead time of the order placed in each period; inf = lost
    p: list[float]
    h: list[float]
    train: list[float]
    dates: list[str] = field(default_factory=list)

    @property
    def T(self) -> int:
        return len(self.demand)


def _lead(v: str) -> float:
    return INF if str(v).strip().lower() == "inf" else float(int(float(v)))


def rels() -> list[str]:
    out = [p.parent.relative_to(BENCH).as_posix() for p in BENCH.rglob("test.csv")]
    return sorted(out)


def load(rel: str) -> Instance:
    d = BENCH / rel
    with open(d / "test.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    item = next(c for c in rows[0] if c.startswith("demand_"))[len("demand_"):]
    with open(d / "train.csv", newline="", encoding="utf-8") as fh:
        train = [float(r[f"demand_{item}"]) for r in csv.DictReader(fh)]
    parts = rel.split("/")
    kind = "real" if parts[0].startswith("real") else "synthetic"
    if kind == "synthetic":
        family = parts[2]
        cluster = "/".join(parts[2:4]) + "/" + parts[4].split("_")[0]      # pattern/variant/realization
    else:
        family = "real"
        cluster = "real/" + parts[2]
    return Instance(
        rel=rel, kind=kind, lead_setting=parts[1], family=family, cluster=cluster, promised=PROMISED[parts[1]],
        item=item, demand=[int(float(r[f"demand_{item}"])) for r in rows],
        lead=[_lead(r[f"lead_time_{item}"]) for r in rows],
        p=[float(r[f"profit_{item}"]) for r in rows], h=[float(r[f"holding_cost_{item}"]) for r in rows],
        train=train, dates=[r.get(f"exact_dates_{item}", "") for r in rows])


@dataclass
class Obs:
    """What the environment shows the ordering agent at the start of period t (1-indexed), before it orders."""
    t: int
    on_hand: int
    in_transit: int                 # as the environment reports it: every order not yet arrived, lost ones included
    demands: list[int]              # realised demand of periods 1..t-1 (uncensored)
    orders: list[int]               # own orders of periods 1..t-1
    arrivals: list[tuple[int, int, int]]   # (arrival period, quantity, order period) for periods 1..t-1
    p: float
    h: float


def simulate(policy, inst: Instance) -> list[int]:
    """Run a policy with the environment's timing: order, then arrivals due this period, then demand."""
    on_hand, pending = 0, []                 # pending: [arrival_period, qty, order_period]
    demands, orders, arrivals = [], [], []
    for t in range(1, inst.T + 1):
        obs = Obs(t=t, on_hand=on_hand, in_transit=sum(q for _, q, _ in pending), demands=list(demands),
                  orders=list(orders), arrivals=list(arrivals), p=inst.p[t - 1], h=inst.h[t - 1])
        q = max(0, int(policy.order(obs)))
        orders.append(q)
        if q > 0:
            pending.append([t + inst.lead[t - 1], q, t])
        for a, qty, od in [x for x in pending if x[0] == t]:
            on_hand += qty
            arrivals.append((t, qty, od))
        pending = [x for x in pending if x[0] != t]
        d = inst.demand[t - 1]
        on_hand -= min(d, on_hand)
        demands.append(d)
    return orders


def score(orders: list[int], inst: Instance) -> dict:
    """Reward of an order sequence under the environment's rules, plus the two reference quantities."""
    on_hand, due = 0.0, {}
    profit = holding = sold_total = 0.0
    for t in range(1, inst.T + 1):
        q = float(orders[t - 1])
        if q > 0 and not math.isinf(inst.lead[t - 1]):
            a = t + int(inst.lead[t - 1])
            due[a] = due.get(a, 0.0) + q
        on_hand += due.pop(t, 0.0)
        sold = min(float(inst.demand[t - 1]), on_hand)
        on_hand -= sold
        profit += inst.p[t - 1] * sold
        holding += inst.h[t - 1] * on_hand
        sold_total += sold
    total_demand = float(sum(inst.demand))
    reward = profit - holding
    ub = inst.p[0] * total_demand                       # the benchmark's normaliser (not a feasible policy)
    clair = clairvoyant(inst)
    return {"reward": reward, "profit": profit, "holding": holding, "sold": sold_total, "demand": total_demand,
            "ordered": float(sum(orders)), "service": sold_total / total_demand if total_demand else 1.0,
            "ub": ub, "norm": max(0.0, reward / ub) if ub > 0 else 0.0,
            "clair": clair, "norm_clair": max(0.0, reward / clair) if clair > 0 else 0.0}


def clairvoyant(inst: Instance) -> float:
    """
    Best reward of an agent that knows every future demand and every lead time in advance.

    A unit sold in period t must have arrived in some period a <= t and is then held t - a periods. With full
    foresight each period's demand is served from the latest arrival opportunity not after t, when that pays:
        sum_t d_t * max(0, p - sum of h over the periods the unit is held).
    This is still an upper bound on any policy that cannot see the future.
    """
    arrive = set()
    for t in range(1, inst.T + 1):
        if not math.isinf(inst.lead[t - 1]):
            arrive.add(t + int(inst.lead[t - 1]))
    total, last = 0.0, None
    for t in range(1, inst.T + 1):
        if t in arrive:
            last = t
        if last is None:
            continue
        cost = sum(inst.h[k - 1] for k in range(last, t))        # held at the end of periods last..t-1
        total += inst.demand[t - 1] * max(0.0, inst.p[t - 1] - cost)
    return total


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
