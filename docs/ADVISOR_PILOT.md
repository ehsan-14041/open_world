# Advisor Pilot Kit — Operations Decision Brief Generator

Package OWE for supply chain consultants, fractional operations leaders, and S&OP advisors.

## Offer

- **Price:** $149/month advisor plan (unlimited briefs) or $2,500–8,000 per 20-site cohort pilot (90 days)
- **Deliverable:** White-label decision memo PDF per operational decision (safety stock, expedite, supplier switch, demand reallocation)
- **Trial:** 10 free briefs — no API key required

## Demo script (2 minutes)

1. Open `http://127.0.0.1:5081`
2. Load **Strained — demand spike, capacity tight** preset (or enter a real client's numbers)
3. Pick **Increase safety stock** vs **Expedite reorder** comparison
4. Adjust editable assumptions (e.g. holding cost, lead time reduction) to match the client's context
5. Click **Simulate this decision**
6. **Save to journal** → **Export PDF** with your advisor name in the header
7. Send PDF to the VP Operations / planning lead before the S&OP review

## White-label PDF

On the results card:

1. Enter **Advisor / firm name** (optional)
2. Click **Export PDF** — opens a print-ready view; save as PDF from the browser

## Objection handling

| Objection | Response |
|-----------|----------|
| "Our ERP / spreadsheet does this" | Same question, but structured memo, editable assumptions, decision log, and 30-day outcome check-in |
| "Numbers are wrong" | Assumptions are editable; product is directional, not a forecast |
| "Ops leaders won't pay" | You bill for the memo as part of your advisory retainer |

## Outbound targets

- Fractional VP Operations / supply chain consultants on LinkedIn
- S&OP program leads and planning directors at mid-market manufacturers and distributors
- Operations advisory firms prepping clients for quarterly business reviews

## Success metrics (90 days)

- 3 paying advisor accounts
- 50+ journal entries with operational decisions saved
- 20%+ annotation rate on 30-day check-ins

## Disable engineering UI for demos

Product mode is on by default (`product_mode: true` in `config/settings.json`). Engineering routes (`/advanced`, `/dashboard`, `/viewer`) are hidden.

To re-enable for internal development:

```bash
set OWE_PRODUCT_MODE=false
python ui.py
```
