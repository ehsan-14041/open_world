<?php /** Password gate. Variables in scope: $heading, $error. */ ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title><?= htmlspecialchars($heading, ENT_QUOTES) ?></title>
<style>
:root{--paper:#F7F6F1;--card:#fff;--ink:#1E2A30;--muted:#5B6B72;--rule:#DFE2DB;--b:#1F7A5C;--crit:#B5463A}
@media (prefers-color-scheme:dark){:root{--paper:#15191B;--card:#1C2124;--ink:#E8EAE4;--muted:#9AA6AB;--rule:#2B3236;--b:#4FB58E;--crit:#E07A6E}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:var(--paper);color:var(--ink);
     font:17px/1.5 "Source Sans 3","Segoe UI",system-ui,-apple-system,sans-serif}
.box{background:var(--card);border:1px solid var(--rule);border-radius:16px;padding:32px;width:100%;max-width:400px;
     box-shadow:0 1px 2px rgba(30,42,48,.06),0 8px 24px -12px rgba(30,42,48,.12)}
h1{margin:0 0 6px;font:500 26px/1.2 Fraunces,Georgia,serif;letter-spacing:-.01em}
p{margin:0 0 22px;color:var(--muted);font-size:15px}
label{display:block;font-size:14px;font-weight:600;margin-bottom:6px}
input{width:100%;padding:12px 14px;font:inherit;color:inherit;background:var(--paper);
      border:1px solid var(--rule);border-radius:10px;min-height:48px}
input:focus-visible{outline:2px solid var(--b);outline-offset:2px}
button{width:100%;margin-top:16px;padding:13px;font:600 16px/1 inherit;color:#fff;background:var(--b);
       border:0;border-radius:999px;cursor:pointer;min-height:48px}
.err{color:var(--crit);font-size:14px;margin-top:12px}
</style>
</head>
<body>
<form class="box" method="post" autocomplete="off">
  <h1><?= htmlspecialchars($heading, ENT_QUOTES) ?></h1>
  <p>This comparison is shared privately. Enter the password you were given.</p>
  <label for="p">Password</label>
  <input id="p" name="password" type="password" autofocus required>
  <button type="submit">Open</button>
  <?php if ($error !== ''): ?><div class="err"><?= htmlspecialchars($error, ENT_QUOTES) ?></div><?php endif; ?>
</form>
</body>
</html>
