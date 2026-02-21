/**
 * Tests for Run Viewer UI inference and diff utilities.
 * Run with: node tests/run_viewer_inference_test.js
 */

const assert = require('assert');

function getState(obj, key) {
  const v = obj && obj[key];
  return v !== undefined && v !== null ? v : null;
}

function getTurnState(turn) {
  if (!turn || typeof turn !== 'object') return {};
  let vars = turn.variables || turn.global_state;
  if (vars && typeof vars === 'object') return vars;
  if (typeof turn === 'object' && !Array.isArray(turn)) return turn;
  return {};
}

function isNumeric(x) {
  return typeof x === 'number' && x === x;
}

function inferTurns(json) {
  if (!json || typeof json !== 'object') return { turns: [], count: 0, inferred: false };
  let turns = getState(json, 'turns');
  if (Array.isArray(turns) && turns.length > 0) {
    return { turns, count: turns.length, inferred: true };
  }
  if (Array.isArray(json)) {
    const list = json.filter((t) => {
      return t && typeof t === 'object' && (typeof t.turn === 'number' || (getTurnState(t) && Object.keys(getTurnState(t)).length > 0));
    });
    if (list.length > 0) return { turns: list, count: list.length, inferred: true };
  }
  return { turns: [json], count: 1, inferred: true };
}

function inferFinalState(json) {
  if (!json || typeof json !== 'object') return null;
  let final = getState(json, 'final');
  if (final && typeof final === 'object') {
    const v = final.variables || final.global_state;
    if (v && typeof v === 'object') return v;
    return final;
  }
  const g = getState(json, 'global_state');
  if (g && typeof g === 'object') return g;
  const v = getState(json, 'variables');
  if (v && typeof v === 'object') return v;
  const inferred = inferTurns(json);
  if (inferred.turns.length > 0) {
    const last = inferred.turns[inferred.turns.length - 1];
    return getTurnState(last);
  }
  return null;
}

function inferTurnDeltas(turn, prevState, nextState) {
  const out = [];
  function addDelta(varName, delta, beforeVal, afterVal) {
    const d = parseFloat(delta);
    if (!isNumeric(d)) return;
    out.push({ var: varName, delta: d, before: beforeVal, after: afterVal });
  }
  const vc = turn && turn.variable_changes;
  if (Array.isArray(vc)) {
    for (let i = 0; i < vc.length; i++) {
      const c = vc[i];
      if (c && c.var != null) addDelta(c.var, c.delta, c.before, c.after);
    }
    out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    return out;
  }
  const tr = turn && turn.turn_record;
  if (tr && tr.delta_applied && typeof tr.delta_applied === 'object') {
    for (const k in tr.delta_applied) {
      if (Object.prototype.hasOwnProperty.call(tr.delta_applied, k))
        addDelta(k, tr.delta_applied[k], null, null);
    }
    out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    return out;
  }
  const delta = turn && turn.delta;
  const nu = (delta && delta.numeric_updates) || (turn && turn.numeric_updates) || (turn && turn.updates) || (turn && turn.global_world_delta) || (turn && turn.variable_updates);
  if (nu && typeof nu === 'object') {
    for (const key in nu) {
      if (Object.prototype.hasOwnProperty.call(nu, key)) addDelta(key, nu[key], null, null);
    }
    out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    return out;
  }
  if (prevState && nextState && typeof prevState === 'object' && typeof nextState === 'object') {
    const allKeys = {};
    for (const p in prevState) if (Object.prototype.hasOwnProperty.call(prevState, p)) allKeys[p] = true;
    for (const n in nextState) if (Object.prototype.hasOwnProperty.call(nextState, n)) allKeys[n] = true;
    for (const k in allKeys) {
      const prevVal = prevState[k];
      const nextVal = nextState[k];
      if (isNumeric(prevVal) || isNumeric(nextVal)) {
        const pn = isNumeric(prevVal) ? prevVal : 0;
        const nn = isNumeric(nextVal) ? nextVal : 0;
        const d = nn - pn;
        if (d !== 0) addDelta(k, d, pn, nn);
      }
    }
    out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  }
  return out;
}

function inferNumericVariables(turns) {
  const keys = {};
  for (let i = 0; i < turns.length; i++) {
    const state = getTurnState(turns[i]);
    for (const k in state) {
      if (Object.prototype.hasOwnProperty.call(state, k) && isNumeric(state[k])) keys[k] = true;
    }
  }
  return Object.keys(keys);
}

function diffFinalState(finalA, finalB) {
  if (!finalA || typeof finalA !== 'object') finalA = {};
  if (!finalB || typeof finalB !== 'object') finalB = {};
  const allKeys = {};
  for (const k in finalA) if (Object.prototype.hasOwnProperty.call(finalA, k)) allKeys[k] = true;
  for (const k in finalB) if (Object.prototype.hasOwnProperty.call(finalB, k)) allKeys[k] = true;
  const out = [];
  for (const k in allKeys) {
    const a = finalA[k];
    const b = finalB[k];
    if (typeof a === 'number' && a === a && typeof b === 'number' && b === b) {
      const d = b - a;
      if (d !== 0) out.push({ var: k, a, b, delta: d, absDelta: Math.abs(d) });
    }
  }
  out.sort((x, y) => y.absDelta - x.absDelta);
  return out;
}

function main() {
  let r = inferTurns({ turns: [{ variables: { x: 1 } }, { variables: { x: 2 } }], final: { variables: { x: 2 } } });
  assert.strictEqual(r.count, 2);
  assert.strictEqual(r.turns.length, 2);
  assert.strictEqual(r.inferred, true);

  r = inferTurns([{ variables: { a: 1 } }, { variables: { a: 2 } }]);
  assert.strictEqual(r.count, 2);
  assert.strictEqual(r.turns[0].variables.a, 1);

  r = inferTurns({ variables: { x: 1 } });
  assert.strictEqual(r.count, 1);
  assert.strictEqual(r.turns[0].variables.x, 1);

  // Format: entities, relations, variables (snapshot from simulation)
  const snapshotFormat = {
    entities: {},
    relations: [],
    variables: {
      diplomatic_engagement_level: 60,
      economic_stability_iran: 35.3,
      trust_between_parties: 32.65,
    },
  };
  r = inferTurns(snapshotFormat);
  assert.strictEqual(r.count, 1, 'snapshot format should infer 1 turn');
  assert.strictEqual(r.turns[0].variables.diplomatic_engagement_level, 60);
  const snapshotFinal = inferFinalState(snapshotFormat);
  assert.strictEqual(snapshotFinal.diplomatic_engagement_level, 60);
  assert.strictEqual(snapshotFinal.trust_between_parties, 32.65);

  let final = inferFinalState({ final: { variables: { x: 10 } } });
  assert.strictEqual(final.x, 10);

  final = inferFinalState({ turns: [{ variables: { x: 1 } }, { variables: { x: 5 } }] });
  assert.strictEqual(final.x, 5);

  let deltas = inferTurnDeltas({ variable_changes: [{ var: 'cash', delta: -10 }, { var: 'growth', delta: 2 }] }, null, null);
  assert.strictEqual(deltas.length, 2);
  assert.strictEqual(deltas[0].var, 'cash');
  assert.strictEqual(deltas[0].delta, -10);

  deltas = inferTurnDeltas({}, { x: 5, y: 10 }, { x: 8, y: 10 });
  assert.strictEqual(deltas.length, 1);
  assert.strictEqual(deltas[0].var, 'x');
  assert.strictEqual(deltas[0].delta, 3);
  assert.strictEqual(deltas[0].before, 5);
  assert.strictEqual(deltas[0].after, 8);

  const vars = inferNumericVariables([
    { variables: { a: 1, b: 2, c: 'x' } },
    { variables: { a: 3, b: 4, d: 5 } },
  ]);
  assert.ok(vars.includes('a'));
  assert.ok(vars.includes('b'));
  assert.ok(vars.includes('d'));
  assert.ok(!vars.includes('c'));

  let diffs = diffFinalState({ a: 1, b: 10 }, { a: 2, b: 10 });
  assert.strictEqual(diffs.length, 1);
  assert.strictEqual(diffs[0].var, 'a');
  assert.strictEqual(diffs[0].a, 1);
  assert.strictEqual(diffs[0].b, 2);
  assert.strictEqual(diffs[0].delta, 1);

  diffs = diffFinalState({ x: 0, y: 5 }, { x: 10, y: 0 });
  assert.strictEqual(diffs.length, 2);
  assert.strictEqual(diffs[0].absDelta >= diffs[1].absDelta, true);

  console.log('All run_viewer inference and diff tests passed.');
}

main();
