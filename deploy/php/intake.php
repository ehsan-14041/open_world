<?php /** Server-side intake. In scope: $wedge, $fields, $input, $errors, $assist, $assistOn, $description, $languages, $lang, $wedgeId. */ ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Run the comparison for your business</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>
:root{--paper:#F7F6F1;--card:#fff;--ink:#1E2A30;--muted:#5B6B72;--rule:#DFE2DB;--b:#1F7A5C;--c:#A97A12;--crit:#B5463A;--paper2:#EFEEE7}
@media (prefers-color-scheme:dark){:root{--paper:#15191B;--card:#1C2124;--ink:#E8EAE4;--muted:#9AA6AB;--rule:#2B3236;--b:#4FB58E;--c:#D3A230;--crit:#E07A6E;--paper2:#222829}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);padding:32px 20px 64px;
     font:17px/1.5 "Source Sans 3","Segoe UI",system-ui,-apple-system,sans-serif;font-variant-numeric:tabular-nums}
.wrap{max-width:760px;margin:0 auto}
h1{font:500 clamp(28px,5vw,40px)/1.1 Fraunces,Georgia,serif;letter-spacing:-.015em;margin:0 0 10px}
h2{font:500 21px/1.2 Fraunces,Georgia,serif;margin:0 0 6px}
.lede{color:var(--muted);margin:0 0 28px;max-width:56ch}
.card{background:var(--card);border:1px solid var(--rule);border-radius:16px;padding:24px;margin-bottom:20px;
      box-shadow:0 1px 2px rgba(30,42,48,.06),0 8px 24px -12px rgba(30,42,48,.12)}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
label{display:block;font-size:14px;font-weight:600;margin-bottom:6px}
.in{display:flex;align-items:center;border:1px solid var(--rule);border-radius:10px;background:var(--paper);overflow:hidden}
.in .u{padding:0 12px;color:var(--muted);font-size:14px;border-right:1px solid var(--rule);min-height:48px;display:grid;place-items:center}
.in .u.r{border-right:0;border-left:1px solid var(--rule)}
input,textarea{flex:1;min-width:0;border:0;background:transparent;padding:12px;font:inherit;color:inherit;min-height:48px}
textarea{width:100%;border:1px solid var(--rule);border-radius:10px;background:var(--paper);min-height:110px;resize:vertical;line-height:1.5}
input:focus-visible,textarea:focus-visible{outline:2px solid var(--b);outline-offset:-2px}
.hint{font-size:13px;color:var(--muted);margin-top:5px}
.was{font-size:12.5px;color:var(--c);margin-top:5px}
button{margin-top:22px;padding:14px 26px;font:600 16px/1 inherit;color:#fff;background:var(--b);
       border:0;border-radius:999px;cursor:pointer;min-height:50px}
button.ghost{background:var(--paper2);color:inherit;border:1px solid var(--rule)}
a{color:var(--b)}
.errs{border-left:3px solid var(--crit);background:rgba(181,70,58,.08);padding:14px 18px;border-radius:0 10px 10px 0;margin-bottom:24px}
.errs ul{margin:6px 0 0;padding-left:20px}
.privacy{font-size:13.5px;color:var(--muted);background:var(--paper2);border-radius:10px;padding:12px 14px;margin-top:14px}
.note{font-size:14px;color:var(--muted);margin-top:22px;max-width:62ch}
.assist-note{border-left:3px solid var(--c);background:rgba(169,122,18,.09);padding:12px 16px;border-radius:0 10px 10px 0;margin-top:16px;font-size:14.5px}
.langs{font-size:14px;color:var(--muted);margin-bottom:20px}
</style>
</head>
<body>
<div class="wrap">
  <h1>Run the comparison for your <?= htmlspecialchars(strtolower(explode(" /", $wedge["wedge"]["business"])[0]), ENT_QUOTES) ?></h1>
  <p class="lede"><?= count($fields) ?> figures from your books. The comparison itself does not
     change — only your starting position does.</p>

  <?php if (!empty($languages)): ?>
    <div class="langs">Language:
      <a href="?w=<?= urlencode($wedgeId) ?>&amp;new=1">English</a>
      <?php foreach ($languages as $l): ?>
        · <a href="?w=<?= urlencode($wedgeId) ?>&amp;new=1&amp;lang=<?= urlencode($l['code']) ?>"><?= htmlspecialchars($l['label'], ENT_QUOTES) ?></a>
      <?php endforeach; ?>
    </div>
  <?php endif; ?>

  <?php if ($errors): ?>
    <div class="errs"><strong>Please check these:</strong><ul>
      <?php foreach ($errors as $e): ?><li><?= htmlspecialchars($e, ENT_QUOTES) ?></li><?php endforeach; ?>
    </ul></div>
  <?php endif; ?>

  <?php if (!empty($assistOn)): ?>
    <form class="card" method="post" action="./">
      <input type="hidden" name="form_action" value="assist">
      <input type="hidden" name="w" value="<?= htmlspecialchars($wedgeId, ENT_QUOTES) ?>">
      <input type="hidden" name="lang" value="<?= htmlspecialchars((string) ($lang ?? ''), ENT_QUOTES) ?>">
      <h2>Or just describe it</h2>
      <p class="hint" style="margin-bottom:12px">Write it the way you would say it. The fields below get
         filled in as a draft — you check and correct them before anything is calculated.</p>
      <textarea name="description" placeholder="We do about 32,000 a month, roughly 140 orders a day. Coffee and milk run about 11,000. Rent, wages and bills come to 20,500. There is 6,000 in the account. Our supplier just put prices up 40%."><?= htmlspecialchars((string) ($description ?? ''), ENT_QUOTES) ?></textarea>
      <div class="privacy"><strong>This one sends what you type</strong> to the language-model provider this
         site is configured to use, so it can read the figures out of it. Your form entries below are not
         sent anywhere — they are calculated on this server. If you would rather not, just fill the fields in yourself.</div>
      <button class="ghost" type="submit">Read my description</button>
    </form>

    <?php if (!empty($assist) && $assist['ok']): ?>
      <div class="assist-note">
        Filled in <?= count($assist['fields']) ?> field(s) from what you wrote — please check each one.
        <?php if ($assist['missing']): ?>
          <br>Not found, so left empty: <?= htmlspecialchars(implode(', ', array_map(
              fn ($k) => $fields[$k][0] ?? $k, $assist['missing'])), ENT_QUOTES) ?>.
        <?php endif; ?>
        <?php if ($assist['note'] !== ''): ?>
          <br><?= htmlspecialchars($assist['note'], ENT_QUOTES) ?>
        <?php endif; ?>
      </div>
    <?php endif; ?>
  <?php endif; ?>

  <form class="card" method="post" action="./">
    <input type="hidden" name="form_action" value="run">
    <input type="hidden" name="w" value="<?= htmlspecialchars($wedgeId, ENT_QUOTES) ?>">
    <input type="hidden" name="lang" value="<?= htmlspecialchars((string) ($lang ?? ''), ENT_QUOTES) ?>">
    <h2>Your figures</h2>
    <div class="fields" style="margin-top:16px">
      <?php foreach ($fields as $key => [$label, $unit, $hint, $type]): ?>
        <div>
          <label for="f_<?= $key ?>"><?= htmlspecialchars($label, ENT_QUOTES) ?></label>
          <div class="in">
            <?php if ($unit === '$'): ?><span class="u">$</span><?php endif; ?>
            <input id="f_<?= $key ?>" name="<?= $key ?>"
                   <?= $type === 'number' ? 'type="number" inputmode="decimal" step="any"' : 'type="text"' ?>
                   value="<?= htmlspecialchars((string) ($input[$key] ?? ''), ENT_QUOTES) ?>">
            <?php if ($unit === '%'): ?><span class="u r">%</span><?php endif; ?>
          </div>
          <?php if (!empty($assist['evidence'][$key])): ?>
            <div class="was">read from: “<?= htmlspecialchars($assist['evidence'][$key], ENT_QUOTES) ?>”</div>
          <?php endif; ?>
          <?php if ($hint !== ''): ?><div class="hint"><?= htmlspecialchars($hint, ENT_QUOTES) ?></div><?php endif; ?>
        </div>
      <?php endforeach; ?>
    </div>
    <button type="submit">Run my comparison</button>
  </form>

  <p class="note">This runs the full sweep on the server — all 162 assumption combinations, for your
     own low-margin share rather than the nearest tested value. It takes a moment.
     <a href="?w=<?= urlencode($wedgeId) ?>">Back to the demo</a> · <a href="./">choose another business</a>.</p>
</div>
</body>
</html>
