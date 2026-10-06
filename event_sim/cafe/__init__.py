"""
Cafe cost-shock decision comparison — the commercial wedge.

One customer question: "My ingredient costs went up. What happens under different responses?"
Three worlds, one model, one set of assumptions; only the decision differs.

The package is split along the line the engine draws:

  * `worlds`      — the shock and the three decisions, as engine events/interventions
  * `accounting`  — revenue, gross profit, cash: identities over engine trajectories
  * `baseline`    — the fictional demo cafe, and the intake structure a real cafe fills in
  * `run`         — run A/B/C through the real engine and translate to business quantities
  * `sensitivity` — which assumption could change the ranking
  * `evidence`    — every assumption, classified, with its source or its admission that it
                    has none
  * `report`      — the customer-facing HTML and the reproducibility record

Nothing numerical in the comparison comes from an LLM. The engine produces the behavioural
trajectories; the accounting layer applies definitions to them; that is all.
"""
