<?php /** Server-side intake. In scope: $heading, $input, $errors, FIELDS. */ ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Run the comparison for your cafe</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>
:root{--paper:#F7F6F1;--card:#fff;--ink:#1E2A30;--muted:#5B6B72;--rule:#DFE2DB;--b:#1F7A5C;--crit:#B5463A}
@media (prefers-color-scheme:dark){:root{--paper:#15191B;--card:#1C2124;--ink:#E8EAE4;--muted:#9AA6AB;--rule:#2B3236;--b:#4FB58E;--crit:#E07A6E}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);padding:32px 20px 64px;
     font:17px/1.5 "Source Sans 3","Segoe UI",system-ui,-apple-system,sans-serif;font-variant-numeric:tabular-nums}
.wrap{max-width:760px;margin:0 auto}
h1{font:500 clamp(28px,5vw,40px)/1.1 Fraunces,Georgia,serif;letter-spacing:-.015em;margin:0 0 10px}
.lede{color:var(--muted);margin:0 0 28px;max-width:56ch}
.card{background:var(--card);border:1px solid var(--rule);border-radius:16px;padding:24px;
      box-shadow:0 1px 2px rgba(30,42,48,.06),0 8px 24px -12px rgba(30,42,48,.12)}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
label{display:block;font-size:14px;font-weight:600;margin-bottom:6px}
.in{display:flex;align-items:center;border:1px solid var(--rule);border-radius:10px;background:var(--paper);overflow:hidden}
.in .u{padding:0 12px;color:var(--muted);font-size:14px;border-right:1px solid var(--rule);min-height:48px;display:grid;place-items:center}
.in .u.r{border-right:0;border-left:1px solid var(--rule)}
input{flex:1;min-width:0;border:0;background:transparent;padding:12px;font:inherit;color:inherit;min-height:48px}
input:focus-visible{outline:2px solid var(--b);outline-offset:-2px}
.hint{font-size:13px;color:var(--muted);margin-top:5px}
button{margin-top:24px;padding:14px 26px;font:600 16px/1 inherit;color:#fff;background:var(--b);
       border:0;border-radius:999px;cursor:pointer;min-height:50px}
a{color:var(--b)}
.errs{border-left:3px solid var(--crit);background:rgba(181,70,58,.08);padding:14px 18px;border-radius:0 10px 10px 0;margin-bottom:24px}
.errs ul{margin:6px 0 0;padding-left:20px}
.note{font-size:14px;color:var(--muted);margin-top:22px;max-width:62ch}
</style>
</head>
<body>
<div class="wrap">
  <h1>Run the comparison for your cafe</h1>
  <p class="lede">Eight figures from your books. The comparison itself does not change — only your
     starting position does. Nothing is stored and nothing is sent anywhere.</p>

  <?php if ($errors): ?>
    <div class="errs"><strong>Please check these:</strong><ul>
      <?php foreach ($errors as $e): ?><li><?= htmlspecialchars($e, ENT_QUOTES) ?></li><?php endforeach; ?>
    </ul></div>
  <?php endif; ?>

  <form class="card" method="post" action="./">
    <div class="fields">
      <?php foreach (FIELDS as $key => [$label, $unit, $hint, $type]): ?>
        <div>
          <label for="f_<?= $key ?>"><?= htmlspecialchars($label, ENT_QUOTES) ?></label>
          <div class="in">
            <?php if ($unit === '$'): ?><span class="u">$</span><?php endif; ?>
            <input id="f_<?= $key ?>" name="<?= $key ?>"
                   <?= $type === 'number' ? 'type="number" inputmode="decimal" step="any"' : 'type="text"' ?>
                   value="<?= htmlspecialchars((string) ($input[$key] ?? ''), ENT_QUOTES) ?>">
            <?php if ($unit === '%'): ?><span class="u r">%</span><?php endif; ?>
          </div>
          <?php if ($hint !== ''): ?><div class="hint"><?= htmlspecialchars($hint, ENT_QUOTES) ?></div><?php endif; ?>
        </div>
      <?php endforeach; ?>
    </div>
    <button type="submit">Run my comparison</button>
  </form>

  <p class="note">This runs the full sweep on the server — all 162 assumption combinations, for your
     own low-margin share rather than the nearest tested value. It takes a moment.
     <a href="./">Back to the demo cafe</a>.</p>
</div>
</body>
</html>
