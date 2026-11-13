# InventoryBench replication (zero LLM calls)

Tests whether simple statistical rules close the gap between the OR baseline and the published LLM results of
InventoryBench (Baek, Fu, Ma, Peng, arXiv 2602.12631). Rules were fixed in [PROTOCOL.md](PROTOCOL.md) before
the new baselines were run. Report (Persian): [`reports/inventorybench_replication/RESULTS.md`](../../reports/inventorybench_replication/RESULTS.md).

Nothing here touches the Open World engine, and no language model is called: the LLM arms are the order
sequences the benchmark's authors published.

## Reproduce

```bash
mkdir -p vendor && git clone https://github.com/TianyiPeng/InventoryBench.git vendor/InventoryBench
git -C vendor/InventoryBench checkout 62b1f1162f19a41d428d47c6cd4ca431f098f6f3
python phase0.py          # verify the benchmark, reproduce its stored results  -> phase0_results.json
python run_baselines.py   # run and score every arm                              -> scores.json, baseline_orders.json
python analyze.py         # tables and intervals                                 -> analysis.json, analysis.md
```

`vendor/` is ignored by git (1.9 GB) and is never modified. `phase0.py` stops if the clone is not at the pinned
commit. All three scripts are deterministic (bootstrap seed 20261116).

Run on: Python 3.14.4, numpy 2.4.4, pandas 3.0.3, scipy 1.17.1, Windows 10 (10.0.19045). The repository's own
`run_or.py` needs nothing else; its LLM dependencies (`openai`, `python-dotenv`) are not imported by anything
used here.

## Files

| File | What it is |
|---|---|
| `PROTOCOL.md` | questions, baselines, constants, metrics and decision rules, written first |
| `ib.py` | instance loader, simulator with the environment's timing, scorer, feasible-clairvoyant bound |
| `policies.py` | the OR replica and the five baselines, plus the declared sensitivity variants |
| `phase0.py` | benchmark verification and reproduction of stored results |
| `run_baselines.py` | runs every policy on all 1,320 instances; policies are built without access to `test.csv` |
| `analyze.py` | level tables, paired differences with cluster-bootstrap intervals, decision rules |
| `phase0_results.json`, `analysis.json`, `analysis.md` | outputs |
| `scores.json`, `baseline_orders.json` | per-instance scores of every arm and the baselines' order sequences |
