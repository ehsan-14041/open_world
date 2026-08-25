"""
Product-level rules that must hold for every wedge.

The commercial claim is the same for all three: same business, same assumptions, same model,
different decision — a comparison of scenarios, never a prediction. These tests hold that
claim across the whole family, so adding a wedge cannot quietly weaken it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from event_sim.wedge.evidence import ASSUMPTION, CUSTOMER, DERIVED, RESEARCH
from event_sim.wedge.registry import CHOOSER, WEDGES
from event_sim.wedge.report import TEMPLATE

ROOT = Path(__file__).resolve().parent.parent

#: Affirmative overclaims. Bare words will not do: the reports deliberately SAY "not a
#: prediction" and list "Predict the future or guarantee an outcome" among the things they do
#: not do, and a check that cannot tell a disclaimer from a claim would push that honesty out
#: of the product. These patterns match the claim and leave the denial alone.
OVERCLAIM_PATTERNS = (
    r"we (?:predict|forecast)",
    r"(?:predicts|forecasts|will happen|is guaranteed|guaranteed (?:to|outcome|result))",
    r"(?:the|an|is the) optimal",
    r"optimal (?:decision|choice|price|answer)",
    r"probability (?:of|that)",
    r"\d+\s?% (?:chance|likely|probability)",
    r"(?:high|low)?\s?confidence (?:that|interval|level)",
    r"AI (?:recommends|suggests|advises)",
    r"scientifically validated",
    r"you should choose",
    r"recommended (?:option|decision|choice)",
)


def overclaims(text: str) -> list[str]:
    """Affirmative overclaims in a blob of customer-facing copy, ignoring denials of them."""
    return [p for p in OVERCLAIM_PATTERNS if re.search(p, text, flags=re.I)]

WEDGE_IDS = sorted(WEDGES)


@pytest.mark.parametrize("wedge_id", WEDGE_IDS)
def test_every_wedge_declares_the_whole_contract(wedge_id):
    w = WEDGES[wedge_id]
    assert w.business and w.question and w.module_id
    assert w.horizon_days == 90
    assert (ROOT / "world_models" / "small_business" / f"{w.module_id}.json").is_file()
    for key in ("world_names", "world_short", "headline", "hero_lede", "unit_word",
                "cost_word", "sens_values", "sens_help", "limits_does_not",
                "intake_groups", "fields", "primary_axis", "research_settings"):
        assert key in w.copy, f"{wedge_id} is missing copy.{key}"
    assert set(w.copy["world_names"]) == {"A", "B", "C"}


@pytest.mark.parametrize("wedge_id", WEDGE_IDS)
def test_the_intake_stays_short_enough_to_finish_in_two_minutes(wedge_id):
    w = WEDGES[wedge_id]
    assert 6 <= len(w.intake_fields) <= 10, f"{wedge_id} asks for {len(w.intake_fields)} fields"
    # Every field the form offers must be a real field on the baseline, and vice versa.
    demo = w.demo_factory().to_dict()
    for f in w.intake_fields:
        assert f["key"] in demo, f"{wedge_id}: intake field {f['key']} is not on the baseline"
        assert f["label"] and f["hint"] is not None
    grouped = [k for g in w.copy["intake_groups"] for k in g["fields"]]
    assert sorted(grouped) == sorted(f["key"] for f in w.intake_fields), (
        f"{wedge_id}: the grouped form and the intake fields disagree")


@pytest.mark.parametrize("wedge_id", WEDGE_IDS)
def test_the_swept_grid_is_finite_explicit_and_labelled(wedge_id):
    w = WEDGES[wedge_id]
    assert w.sweep, "sensitivity must run over an explicit grid"
    assert set(w.sweep) == set(w.sweep_labels), f"{wedge_id}: every swept axis needs a label"
    total = 1
    for values in w.sweep.values():
        assert len(values) >= 2
        total *= len(values)
    assert total == 162, f"{wedge_id} grid is {total} points"


@pytest.mark.parametrize("wedge_id", WEDGE_IDS)
def test_no_customer_facing_copy_predicts_or_gives_odds(wedge_id):
    w = WEDGES[wedge_id]
    strings = []
    def walk(v):
        if isinstance(v, str):
            strings.append(v)
        elif isinstance(v, dict):
            [walk(x) for x in v.values()]
        elif isinstance(v, list):
            [walk(x) for x in v]
    walk({k: v for k, v in w.copy.items() if not callable(v)})
    walk(w.question)
    blob = " ".join(strings)
    assert not overclaims(blob), f"{wedge_id}: overclaim in customer copy: {overclaims(blob)}"
    # And the denial must actually be there.
    assert any("Predict the future" in x for x in w.copy["limits_does_not"])


@pytest.mark.parametrize("wedge_id", WEDGE_IDS)
def test_every_assumption_is_classified_and_traceable(wedge_id):
    w = WEDGES[wedge_id]
    baseline = w.demo_factory()
    reg = w.build_registry(baseline, axis_settings=dict(w.default_axes),
                           custom_elasticity=None, **w.knob_defaults)
    assert len(reg) >= 12, f"{wedge_id} declares only {len(reg)} assumptions"
    for a in reg:
        assert a.klass in (CUSTOMER, RESEARCH, ASSUMPTION, DERIVED), a.key
        assert a.label and a.value != ""
        if a.klass == RESEARCH:
            assert a.source, f"{wedge_id}.{a.key}: classed as research with no source named"
    # Anything claimed as research must name a source this wedge actually carries.
    ids = {s["id"] for s in w.sources}
    for a in reg:
        if a.klass == RESEARCH:
            assert any(i in a.source for i in ids), f"{wedge_id}.{a.key}: source not in the wedge's list"


@pytest.mark.parametrize("wedge_id", WEDGE_IDS)
def test_price_sensitivity_is_only_called_research_where_a_study_backs_it(wedge_id):
    """
    The salon has no usable published elasticity, so it must never be labelled research at any
    setting. The shop's published figure is brand-level and backs only the high setting.
    """
    w = WEDGES[wedge_id]
    baseline = w.demo_factory()
    for setting in ("low", "central", "high"):
        reg = w.build_registry(baseline, axis_settings={**w.default_axes, "price_sensitivity": setting},
                               custom_elasticity=None, **w.knob_defaults)
        row = next(a for a in reg if a.key == "price_sensitivity")
        backed = setting in w.copy["research_settings"]
        assert (row.klass == RESEARCH) == backed, (
            f"{wedge_id} at {setting}: classed {row.klass} but research_settings says {backed}")
    if wedge_id == "salon":
        assert w.copy["research_settings"] == [], "no published salon elasticity exists"


@pytest.mark.parametrize("wedge_id", WEDGE_IDS)
def test_a_customers_own_figures_replace_the_demo_entirely(wedge_id):
    """Demo state must not leak into a real business's report."""
    w = WEDGES[wedge_id]
    demo = w.demo_factory().to_dict()
    real = dict(demo)
    real["name"] = "Real Business Ltd"
    real["is_demo"] = False
    real["monthly_revenue"] = demo["monthly_revenue"] * 1.7
    baseline = w.baseline_from_dict(real)

    assert baseline.is_demo is False
    assert baseline.name == "Real Business Ltd"
    assert baseline.monthly_revenue != w.demo_factory().monthly_revenue

    from event_sim.wedge.compare import run_comparison
    comp = run_comparison(w, baseline)
    record = comp.reproducibility_record()
    assert record["baseline"]["name"] == "Real Business Ltd"
    assert record["baseline"]["is_demo"] is False
    assert record["wedge_id"] == wedge_id
    for world in record["worlds"]:
        assert world["trajectory_fingerprint"], "the record must be reproducible"


def test_the_chooser_offers_exactly_the_three_wedges():
    assert len(CHOOSER) == 3
    assert [c["id"] for c in CHOOSER] == ["cafe", "shop", "salon"]
    for entry in CHOOSER:
        assert entry["id"] in WEDGES
        assert entry["icon"] and entry["business"] and entry["question"]
        assert entry["question"].endswith("?"), "the chooser asks a question in plain language"
    chooser_html = (ROOT / "event_sim" / "wedge" / "templates" / "chooser.html").read_text(encoding="utf-8")
    visible = re.sub(r"<style.*?</style>", "", chooser_html, flags=re.S)
    for jargon in ("elasticity", "fingerprint", "sensitivity", "module", "coefficient",
                   "simulation", "engine", "intervention"):
        assert jargon not in visible.lower(), f"chooser screen uses {jargon!r}"
    assert not overclaims(visible), f"chooser screen overclaims: {overclaims(visible)}"
    assert "not a prediction" in visible, "the chooser must say what this is not"


def test_the_page_never_turns_a_count_into_odds():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "This is a sensitivity count, not a probability." in html
    assert "ranked first in" in html
    for banned in ("% chance", "probability of", "likelihood", "we predict", "will be worth"):
        assert banned not in html.lower()
