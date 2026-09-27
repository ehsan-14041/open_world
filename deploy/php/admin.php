<?php
/**
 * Maintainer settings.
 *
 * Reachable only when `admin_password` is set in config.php — with no admin password this page
 * refuses to load at all, so an unconfigured install cannot expose it. The session is separate
 * from the visitor gate: unlocking the report does not unlock this.
 */
declare(strict_types=1);

require_once __DIR__ . '/lib/compat.php';
require_once __DIR__ . '/lib/llm.php';
require_once __DIR__ . '/lib/i18n.php';
require_once __DIR__ . '/lib/router.php';
require_once __DIR__ . '/lib/feedback.php';

$config = is_file(__DIR__ . '/config.php') ? (require __DIR__ . '/config.php') : [];
$adminPassword = (string) ($config['admin_password'] ?? '');

if ($adminPassword === '') {
    http_response_code(404);
    header('Content-Type: text/plain; charset=utf-8');
    exit("The admin page is off.\n\nSet 'admin_password' in config.php to switch it on.");
}

header('X-Frame-Options: DENY');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
session_start();
if (isset($_GET['logout'])) {
    unset($_SESSION['admin']);
    header('Location: admin.php');
    exit;
}
$loginError = '';
if (empty($_SESSION['admin'])) {
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['admin_password'])) {
        if (hash_equals($adminPassword, (string) $_POST['admin_password'])) {
            session_regenerate_id(true);
            $_SESSION['admin'] = true;
            header('Location: admin.php');
            exit;
        }
        usleep(700000);
        $loginError = 'That is not the admin password.';
    }
    $heading = 'Site settings';
    $error = $loginError;
    header('Content-Type: text/html; charset=utf-8');
    header('Cache-Control: no-store');
    include __DIR__ . '/unlock.php';
    exit;
}

$llm = llm_settings($config);

// ---- downloads: what owners chose to send, as CSV, for whoever reads the evidence ---------
$export = (string) ($_GET['export'] ?? '');
if ($export === 'feedback' || $export === 'bookings' || $export === 'measurements') {
    $files = ['feedback' => FEEDBACK_FILE, 'bookings' => BOOKINGS_FILE,
              'measurements' => __DIR__ . '/data/contrib/measurements.jsonl'];
    $cols = [
        'feedback' => ['at', 'build', 'wedge', 'variant', 'lang', 'demo', 'src', 'real', 'helped',
                       'next', 'hard', 'offer', 'missing', 'anon'],
        'bookings' => ['at', 'build', 'wedge', 'variant', 'lang', 'src', 'price', 'contact', 'anon'],
        'measurements' => ['at', 'wedge', 'variant', 'e', 'rise', 'anon'],
    ];
    header('Content-Type: text/csv; charset=utf-8');
    header('Cache-Control: no-store');
    header('Content-Disposition: attachment; filename="' . $export . '-' . gmdate('Ymd') . '.csv"');
    echo "\xEF\xBB\xBF" . feedback_csv(feedback_rows($files[$export]), $cols[$export]);
    exit;
}

$notice = '';
$problem = '';
$testResult = null;
$generateResult = null;
$modelList = null;

// ---- actions -------------------------------------------------------------------------------
$action = (string) ($_POST['action'] ?? '');

if ($action === 'save') {
    $llm['enabled'] = !empty($_POST['enabled']);
    $llm['base_url'] = trim((string) ($_POST['base_url'] ?? '')) ?: LLM_DEFAULTS['base_url'];
    $llm['model'] = trim((string) ($_POST['model'] ?? ''));
    $llm['timeout_seconds'] = max(5, min(300, (int) ($_POST['timeout_seconds'] ?? 60)));
    $llm['max_output_tokens'] = max(64, min(32000, (int) ($_POST['max_output_tokens'] ?? 4000)));
    $llm['monthly_call_cap'] = max(0, (int) ($_POST['monthly_call_cap'] ?? 200));
    $llm['features'] = [
        'translation' => !empty($_POST['feature_translation']),
        'intake_assistant' => !empty($_POST['feature_intake_assistant']),
        'question_router' => !empty($_POST['feature_question_router']),
    ];
    // An empty key field means "leave it alone", so saving other settings cannot wipe the key.
    $typedKey = trim((string) ($_POST['api_key'] ?? ''));
    if ($typedKey !== '') {
        $llm['api_key'] = $typedKey;
    }
    if (!empty($_POST['clear_key'])) {
        $llm['api_key'] = '';
    }
    if (llm_save_settings($llm)) {
        $notice = 'Settings saved.';
        $llm = llm_settings($config);
    } else {
        $problem = 'Could not write data/settings.json. Make the data/ folder writable.';
    }
} elseif ($action === 'test') {
    $testResult = llm_test($llm);
} elseif ($action === 'models') {
    $modelList = llm_models($llm);
} elseif ($action === 'translate') {
    if (!llm_feature_on($llm, 'translation')) {
        $problem = 'Switch the LLM on and enable translation first.';
    } else {
        $generateResult = i18n_generate(
            $llm,
            (string) ($_POST['lang_code'] ?? ''),
            trim((string) ($_POST['lang_label'] ?? '')),
            (string) ($_POST['lang_dir'] ?? 'ltr')
        );
        if ($generateResult['ok']) {
            array_map('unlink', glob(__DIR__ . '/data/cache/*.gz') ?: []);
            $notice = "Translated {$generateResult['applied']} of "
                . count(i18n_catalogue()) . ' strings in ' . $generateResult['batches'] . ' calls.';
        } else {
            $problem = $generateResult['error'];
        }
    }
} elseif ($action === 'delete_lang') {
    $code = preg_replace('/[^a-z0-9_-]/i', '', (string) ($_POST['code'] ?? ''));
    if ($code !== '' && is_file(I18N_DIR . '/' . $code . '.json')) {
        unlink(I18N_DIR . '/' . $code . '.json');
        array_map('unlink', glob(__DIR__ . '/data/cache/*.gz') ?: []);
        $notice = "Removed the $code translation.";
    }
} elseif ($action === 'clear_cache') {
    $files = glob(__DIR__ . '/data/cache/*.gz') ?: [];
    array_map('unlink', $files);
    $notice = count($files) . ' cached report(s) deleted.';
}

$languages = i18n_available();
$catalogueSize = count(i18n_catalogue());
$usage = llm_usage();
$month = gmdate('Y-m');
$thisMonth = $usage[$month] ?? ['calls' => 0, 'input_tokens' => 0, 'output_tokens' => 0];
$keyFromConfig = !empty($llm['key_from_config']);
$writable = is_writable(__DIR__ . '/data') || is_writable(dirname(SETTINGS_FILE));

header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex, nofollow');
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Site settings</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500&family=Source+Sans+3:wght@400;600;700&display=swap">
<style>
:root{--paper:#F7F6F1;--card:#fff;--ink:#1E2A30;--muted:#5B6B72;--rule:#DFE2DB;--b:#1F7A5C;--c:#A97A12;--crit:#B5463A;--paper2:#EFEEE7}
@media (prefers-color-scheme:dark){:root{--paper:#15191B;--card:#1C2124;--ink:#E8EAE4;--muted:#9AA6AB;--rule:#2B3236;--b:#4FB58E;--c:#D3A230;--crit:#E07A6E;--paper2:#222829}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);padding:32px 20px 80px;
     font:16px/1.55 "Source Sans 3","Segoe UI",system-ui,-apple-system,sans-serif}
.wrap{max-width:820px;margin:0 auto}
h1{font:500 clamp(26px,4vw,36px)/1.1 Fraunces,Georgia,serif;letter-spacing:-.015em;margin:0}
h2{font:500 22px/1.2 Fraunces,Georgia,serif;margin:0 0 4px}
.sub{color:var(--muted);margin:6px 0 0}
.card{background:var(--card);border:1px solid var(--rule);border-radius:14px;padding:22px;margin-top:20px;
      box-shadow:0 1px 2px rgba(30,42,48,.06),0 8px 24px -12px rgba(30,42,48,.12)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:16px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:5px}
input[type=text],input[type=number],input[type=password],select{width:100%;padding:10px 12px;font:inherit;color:inherit;
  background:var(--paper);border:1px solid var(--rule);border-radius:9px;min-height:44px}
input:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid var(--b);outline-offset:2px}
.hint{font-size:12.5px;color:var(--muted);margin-top:4px}
.check{display:flex;gap:9px;align-items:flex-start;margin-top:12px;font-size:15px}
.check input{margin-top:4px;width:17px;height:17px;flex:0 0 auto}
button{padding:11px 20px;font:600 15px/1 inherit;border-radius:999px;cursor:pointer;min-height:44px;
       border:1px solid var(--rule);background:var(--paper2);color:inherit}
button.primary{background:var(--b);border-color:var(--b);color:#fff}
button.danger{color:var(--crit)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:18px}
.msg{padding:12px 16px;border-radius:10px;margin-top:18px;font-size:15px}
.ok{background:rgba(31,122,92,.10);border-left:3px solid var(--b)}
.bad{background:rgba(181,70,58,.10);border-left:3px solid var(--crit)}
.warn{background:rgba(169,122,18,.10);border-left:3px solid var(--c)}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:14.5px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--rule)}
th{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;background:var(--paper2);padding:1px 5px;border-radius:4px}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap}
a{color:var(--b)}
.note{font-size:14px;color:var(--muted);margin-top:14px;max-width:70ch}
details summary{cursor:pointer;font-weight:600;font-size:14px;margin-top:12px}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>Site settings</h1>
    <div><a href="./">View the report</a> &nbsp;·&nbsp; <a href="admin.php?logout=1">Sign out</a></div>
  </div>
  <p class="sub">The model never produces a figure. It translates the wording, and it reads a
     description into the intake form for the owner to check. The comparison itself is computed
     by the engine either way.</p>

  <?php if ($notice !== ''): ?><div class="msg ok"><?= htmlspecialchars($notice, ENT_QUOTES) ?></div><?php endif; ?>
  <?php if ($problem !== ''): ?><div class="msg bad"><?= htmlspecialchars($problem, ENT_QUOTES) ?></div><?php endif; ?>
  <?php if (!$writable): ?>
    <div class="msg warn">The <code>data/</code> folder is not writable, so settings cannot be saved here.
      Make it writable (755 or 775), or put <code>llm_api_key</code>, <code>llm_base_url</code> and
      <code>llm_model</code> in <code>config.php</code> instead.</div>
  <?php endif; ?>

  <?php
    // ---- launch check: what a maintainer should confirm before sending the link to anyone ----
    $visitorPw = (string) ($config['password'] ?? '');
    $offer = feedback_offer($config);
    $checks = [];
    $checks[] = [version_compare(PHP_VERSION, '7.4.0', '>=') ? 'ok' : 'warn',
        'PHP ' . PHP_VERSION . (version_compare(PHP_VERSION, '7.4.0', '>=') ? '' : ' — works, but no longer receives security fixes. Pick 8.1+ in the host panel.')];
    $checks[] = [is_file(__DIR__ . '/VERSION.txt') ? 'ok' : 'warn', is_file(__DIR__ . '/VERSION.txt')
        ? 'Build: <code>' . htmlspecialchars(feedback_build(), ENT_QUOTES) . '</code> — write this on every session sheet.'
        : 'No VERSION.txt: answers cannot be told apart by build. Upload the whole zip.'];
    $checks[] = [$visitorPw === 'change-me' ? 'bad' : 'ok', $visitorPw === 'change-me'
        ? 'The visitor password is still the sample value <code>change-me</code>.'
        : ($visitorPw === '' ? 'Open to anyone with the link (no visitor password).' : 'Behind a visitor password.')];
    $checks[] = [hash_equals($adminPassword, $visitorPw) ? 'bad' : 'ok', hash_equals($adminPassword, $visitorPw)
        ? 'The admin password is the same as the visitor password.' : 'Admin password is separate from the visitor password.'];
    $checks[] = [$writable ? 'ok' : 'bad', $writable ? '<code>data/</code> is writable.'
        : '<code>data/</code> is not writable: nothing an owner sends can be kept.'];
    $checks[] = [is_file(__DIR__ . '/data/.htaccess') ? 'ok' : 'bad', is_file(__DIR__ . '/data/.htaccess')
        ? '<code>data/.htaccess</code> is in place. On Apache it keeps these files off the web; on nginx, deny <code>/data/</code> in the server config and check that <code>data/feedback/feedback.jsonl</code> does not open in a browser.'
        : '<code>data/.htaccess</code> is missing — answers and contacts could be downloaded by anyone. Upload it again.'];
    $checks[] = [feedback_on($config) ? 'ok' : 'warn', feedback_on($config)
        ? '"Did this help?" is asked after a decision sheet.'
        : '"Did this help?" is off: the site will collect no evidence of its own.'];
    $checks[] = [$offer !== null ? 'ok' : 'warn', $offer !== null
        ? 'The paid follow-up is offered at <strong>' . htmlspecialchars($offer, ENT_QUOTES) . '</strong>. Do not change it mid-pilot.'
        : 'No <code>offer_price</code> in config.php: the site does not test willingness to pay.'];
    $checks[] = [llm_feature_on($llm, 'question_router') ? 'warn' : 'ok', llm_feature_on($llm, 'question_router')
        ? 'The question router is on: typed questions are sent (scrubbed) to your provider.'
        : 'The question router is off.'];
  ?>
  <div class="card">
    <h2>Before you share the link</h2>
    <p class="sub">What this host can check about itself. Everything marked in red should be fixed first.</p>
    <?php foreach ($checks as $c): ?>
      <div class="msg <?= $c[0] === 'ok' ? 'ok' : ($c[0] === 'bad' ? 'bad' : 'warn') ?>"><?= $c[1] ?></div>
    <?php endforeach; ?>
  </div>

  <form method="post" class="card">
    <input type="hidden" name="action" value="save">
    <h2>Model access</h2>
    <p class="sub">Any endpoint that speaks the OpenAI chat-completions shape — AvalAI, OpenAI, or a
       gateway of your own. Save the key first, then list the models to see what it can actually use.</p>

    <label class="check"><input type="checkbox" name="enabled" value="1" <?= !empty($llm['enabled']) ? 'checked' : '' ?>>
      <span>Switched on. With this off, nothing here is called and the product behaves exactly as it does
      without an LLM.</span></label>

    <div class="grid">
      <div>
        <label for="base_url">Base URL</label>
        <input id="base_url" type="text" name="base_url" value="<?= htmlspecialchars((string) $llm['base_url'], ENT_QUOTES) ?>">
        <div class="hint">Ends before <code>/chat/completions</code>. Known-good:
          <?php $first = true; foreach (LLM_PRESETS as $name => $preset): ?>
            <?= $first ? '' : ' · ' ?><a href="#" onclick="document.getElementById('base_url').value='<?= $preset ?>';return false"><?= $name ?></a>
            <?php $first = false; endforeach; ?>
          — or any other gateway or proxy that speaks the same shape.</div>
      </div>
      <div>
        <label for="model">Model</label>
        <input id="model" type="text" name="model" list="model_options"
               value="<?= htmlspecialchars((string) $llm['model'], ENT_QUOTES) ?>"
               placeholder="the model id your provider expects">
        <?php if ($modelList !== null && $modelList['ok']): ?>
          <datalist id="model_options">
            <?php foreach ($modelList['models'] as $m): ?>
              <option value="<?= htmlspecialchars($m, ENT_QUOTES) ?>"></option>
            <?php endforeach; ?>
          </datalist>
        <?php endif; ?>
        <div class="hint">Exactly as your provider names it.</div>
      </div>
      <div>
        <label for="api_key">API key</label>
        <input id="api_key" type="password" name="api_key" value="" autocomplete="off"
               placeholder="<?= $keyFromConfig ? 'set in config.php' : htmlspecialchars(llm_mask_key((string) $llm['api_key']), ENT_QUOTES) ?>"
               <?= $keyFromConfig ? 'disabled' : '' ?>>
        <div class="hint">
          <?php if ($keyFromConfig): ?>
            Taken from <code>config.php</code>, which is never served. Edit it there.
          <?php else: ?>
            Leave empty to keep the current key. Stored in <code>data/settings.json</code>; never sent to a browser.
          <?php endif; ?>
        </div>
      </div>
      <div>
        <label for="monthly_call_cap">Monthly call cap</label>
        <input id="monthly_call_cap" type="number" name="monthly_call_cap" min="0"
               value="<?= (int) $llm['monthly_call_cap'] ?>">
        <div class="hint">0 means no cap. Used <?= (int) $thisMonth['calls'] ?> this month.</div>
      </div>
      <div>
        <label for="max_output_tokens">Max output tokens per call</label>
        <input id="max_output_tokens" type="number" name="max_output_tokens" min="64"
               value="<?= (int) $llm['max_output_tokens'] ?>">
      </div>
      <div>
        <label for="timeout_seconds">Timeout (seconds)</label>
        <input id="timeout_seconds" type="number" name="timeout_seconds" min="5" max="300"
               value="<?= (int) $llm['timeout_seconds'] ?>">
      </div>
    </div>

    <h2 style="margin-top:26px">What it is allowed to do</h2>
    <label class="check"><input type="checkbox" name="feature_translation" value="1"
      <?= !empty($llm['features']['translation']) ? 'checked' : '' ?>>
      <span><strong>Translate the report.</strong> Generated once here and cached to disk — a visitor's
      page view never calls the API.</span></label>
    <label class="check"><input type="checkbox" name="feature_intake_assistant" value="1"
      <?= !empty($llm['features']['intake_assistant']) ? 'checked' : '' ?>>
      <span><strong>Intake assistant.</strong> Turns a typed description into draft form fields.
      This one <em>does</em> send what the visitor types to your provider, so the form says so plainly.
      Off by default.</span></label>
    <label class="check"><input type="checkbox" name="feature_question_router" value="1"
      <?= !empty($llm['features']['question_router']) ? 'checked' : '' ?>>
      <span><strong>Question router.</strong> Sorts a question typed into the home-screen box into one
      this tool can answer with numbers, or a topic it cannot. It sends the question text — after
      phone numbers, emails and web addresses are removed — to your provider, and the box says so.
      The provider returns fields only; it never writes what the visitor reads. One call per question,
      counted against the monthly cap. Off by default.</span></label>

    <?php if ($modelList !== null): ?>
      <div class="msg <?= $modelList['ok'] ? 'ok' : 'warn' ?>">
        <?= $modelList['ok']
            ? 'Your key can use ' . count($modelList['models']) . ' model(s). They are now suggested in the Model field: '
              . htmlspecialchars(implode(', ', array_slice($modelList['models'], 0, 12)), ENT_QUOTES)
              . (count($modelList['models']) > 12 ? ' …' : '')
            : htmlspecialchars($modelList['error'], ENT_QUOTES) ?>
      </div>
    <?php endif; ?>

    <div class="row">
      <button class="primary" type="submit">Save settings</button>
      <button type="submit" name="action" value="models" formnovalidate>List available models</button>
      <?php if (!$keyFromConfig && $llm['api_key'] !== ''): ?>
        <label class="check" style="margin:0"><input type="checkbox" name="clear_key" value="1"><span>Delete the stored key</span></label>
      <?php endif; ?>
    </div>
  </form>

  <form method="post" class="card">
    <input type="hidden" name="action" value="test">
    <h2>Connection test</h2>
    <p class="sub">One very short call, to prove the key, the URL and the model name all work.</p>
    <?php if ($testResult !== null): ?>
      <div class="msg <?= $testResult['ok'] ? 'ok' : 'bad' ?>">
        <?= $testResult['ok']
            ? 'Reached the provider. It replied: ' . htmlspecialchars($testResult['text'], ENT_QUOTES)
              . ' (' . (int) ($testResult['usage']['input_tokens'] ?? 0) . ' in / '
              . (int) ($testResult['usage']['output_tokens'] ?? 0) . ' out)'
            : htmlspecialchars($testResult['error'], ENT_QUOTES) ?>
      </div>
    <?php endif; ?>
    <div class="row"><button type="submit">Run the test</button></div>
  </form>

  <form method="post" class="card">
    <input type="hidden" name="action" value="translate">
    <h2>Languages</h2>
    <p class="sub">The catalogue holds <?= $catalogueSize ?> strings. Translation runs on the template
       before any figure is placed in it, so it cannot reach a number. A string whose
       <code>${…}</code> placeholders or tags do not survive is rejected and stays in English.</p>

    <?php if ($languages): ?>
      <table>
        <tr><th>Code</th><th>Name</th><th>Direction</th><th>Strings</th><th>Model</th><th></th></tr>
        <?php foreach ($languages as $lang): ?>
          <tr>
            <td><code><?= htmlspecialchars($lang['code'], ENT_QUOTES) ?></code></td>
            <td><?= htmlspecialchars($lang['label'], ENT_QUOTES) ?></td>
            <td><?= $lang['dir'] ?></td>
            <td><?= $lang['translated'] ?> / <?= $lang['total'] ?></td>
            <td><?= htmlspecialchars($lang['model'], ENT_QUOTES) ?></td>
            <td style="text-align:right">
              <a href="./?lang=<?= urlencode($lang['code']) ?>">view</a>
            </td>
          </tr>
        <?php endforeach; ?>
      </table>
    <?php else: ?>
      <p class="note">No translations yet. The report is served in English.</p>
    <?php endif; ?>

    <?php if ($generateResult !== null && $generateResult['rejected']): ?>
      <details>
        <summary><?= count($generateResult['rejected']) ?> string(s) kept in English</summary>
        <table>
          <tr><th>id</th><th>reason</th></tr>
          <?php foreach ($generateResult['rejected'] as $id => $reason): ?>
            <tr><td><code><?= htmlspecialchars((string) $id, ENT_QUOTES) ?></code></td>
                <td><?= htmlspecialchars((string) $reason, ENT_QUOTES) ?></td></tr>
          <?php endforeach; ?>
        </table>
      </details>
    <?php endif; ?>

    <div class="grid">
      <div>
        <label for="lang_code">Language code</label>
        <input id="lang_code" type="text" name="lang_code" placeholder="fa" value="">
        <div class="hint">Used in the URL: <code>?lang=fa</code></div>
      </div>
      <div>
        <label for="lang_label">Name</label>
        <input id="lang_label" type="text" name="lang_label" placeholder="فارسی">
      </div>
      <div>
        <label for="lang_dir">Direction</label>
        <select id="lang_dir" name="lang_dir">
          <option value="ltr">Left to right</option>
          <option value="rtl">Right to left</option>
        </select>
      </div>
    </div>
    <div class="row">
      <button class="primary" type="submit" <?= llm_feature_on($llm, 'translation') ? '' : 'disabled' ?>>
        Generate the translation
      </button>
      <span class="hint">About <?= (int) ceil($catalogueSize / 25) ?> calls. Re-running replaces the file.</span>
    </div>
    <p class="note">Read it before you show it to a customer. A translation is a draft: you can edit
       <code>data/i18n/&lt;code&gt;.json</code> by hand and the page picks it up immediately.</p>
  </form>

  <form method="post" class="card">
    <input type="hidden" name="action" value="clear_cache">
    <h2>Report cache</h2>
    <p class="sub">Generated reports are cached under <code>data/cache/</code>. A cached report for a
       real cafe contains that owner's figures — clear it when you are done with them.</p>
    <div class="row">
      <button class="danger" type="submit"><?= count(glob(__DIR__ . '/data/cache/*.gz') ?: []) ?> cached — delete them</button>
    </div>
  </form>

  <?php
    $fbRows = feedback_rows(FEEDBACK_FILE);
    $fbSum = feedback_summary($fbRows);
    $booked = feedback_rows(BOOKINGS_FILE);
    $measured = feedback_rows(__DIR__ . '/data/contrib/measurements.jsonl');
    $labels = [
        'real' => 'A decision they actually face', 'helped' => 'The comparison helped',
        'next' => 'What they will do next', 'hard' => 'Hardest number to give',
        'offer' => 'The paid follow-up',
    ];
  ?>
  <div class="card">
    <h2>What owners told us</h2>
    <p class="sub">Only what owners chose to send from the card under their decision sheet.
       Counts, per build, with each browser counted once. Read them against
       <code>docs/pilot/HYPOTHESES.md</code> — the thresholds there were set before these rows existed.
       People who answer are the ones who chose to: this is not a sample of everyone who visited.</p>
    <?php if (!$fbSum): ?>
      <p class="note">Nothing sent yet.</p>
    <?php else: foreach ($fbSum as $build => $b): ?>
      <h3 style="margin:18px 0 0;font-size:16px">Build <code><?= htmlspecialchars((string) $build, ENT_QUOTES) ?></code> —
        <?= (int) $b['owners'] ?> owners, <?= (int) $b['own_numbers'] ?> with their own numbers</h3>
      <table>
        <tr><th>Question</th><th>Answers</th></tr>
        <?php foreach ($labels as $k => $label): if (empty($b['counts'][$k])) { continue; } arsort($b['counts'][$k]); ?>
          <tr><td><?= htmlspecialchars($label, ENT_QUOTES) ?></td><td>
            <?php foreach ($b['counts'][$k] as $v => $n): ?>
              <code><?= htmlspecialchars((string) $v, ENT_QUOTES) ?></code> <?= (int) $n ?> &nbsp;
            <?php endforeach; ?></td></tr>
        <?php endforeach; ?>
        <tr><td>Invitation (<code>src</code>)</td><td>
          <?php arsort($b['src']); foreach ($b['src'] as $v => $n): ?>
            <code><?= htmlspecialchars((string) $v, ENT_QUOTES) ?></code> <?= (int) $n ?> &nbsp;
          <?php endforeach; ?></td></tr>
      </table>
    <?php endforeach; endif; ?>
    <?php $said = array_values(array_filter(array_reverse($fbRows), function ($r) { return !empty($r['missing']); })); ?>
    <?php if ($said): ?>
      <details><summary>What was missing or unclear, in their words (<?= count($said) ?>)</summary>
        <table>
          <?php foreach (array_slice($said, 0, 80) as $r): ?>
            <tr><td><code><?= htmlspecialchars((string) ($r['at'] ?? ''), ENT_QUOTES) ?></code></td>
                <td><?= htmlspecialchars((string) ($r['wedge'] ?? ''), ENT_QUOTES) ?></td>
                <td dir="auto"><?= htmlspecialchars((string) $r['missing'], ENT_QUOTES) ?></td></tr>
          <?php endforeach; ?>
        </table></details>
    <?php endif; ?>
    <p class="note">Price-test results shared by owners: <?= count($measured) ?>.
      Download: <a href="admin.php?export=feedback">answers (CSV)</a> ·
      <a href="admin.php?export=measurements">measurements (CSV)</a></p>
  </div>

  <div class="card">
    <h2>Asked to book the follow-up</h2>
    <p class="sub">Each of these typed a contact and ticked that it may be kept for this purpose only.
       A request to be contacted is not yet a commitment: it counts as one only once a date and the
       price are agreed with them. Delete a contact when asked — remove its line from
       <code>data/feedback/bookings.jsonl</code> — and when the pilot ends.</p>
    <?php if (!$booked): ?>
      <p class="note">None yet.</p>
    <?php else: ?>
      <table>
        <tr><th>Day</th><th>Build</th><th>Business</th><th>Price shown</th><th>Contact</th></tr>
        <?php foreach (array_reverse($booked) as $r): ?>
          <tr><td><code><?= htmlspecialchars((string) ($r['at'] ?? ''), ENT_QUOTES) ?></code></td>
              <td><code><?= htmlspecialchars((string) ($r['build'] ?? ''), ENT_QUOTES) ?></code></td>
              <td><?= htmlspecialchars(trim((string) ($r['wedge'] ?? '') . ' ' . (string) ($r['variant'] ?? '')), ENT_QUOTES) ?></td>
              <td dir="auto"><?= htmlspecialchars((string) ($r['price'] ?? ''), ENT_QUOTES) ?></td>
              <td dir="ltr"><?= htmlspecialchars((string) ($r['contact'] ?? ''), ENT_QUOTES) ?></td></tr>
        <?php endforeach; ?>
      </table>
      <p class="note"><a href="admin.php?export=bookings">Download (CSV)</a> — it holds personal
        contacts: keep the file off shared drives and delete it when the follow-ups are done.</p>
    <?php endif; ?>
  </div>

  <?php $asked = router_read_questions(60); ?>
  <div class="card">
    <h2>Questions owners asked</h2>
    <p class="sub">Only questions a visitor chose to keep, from <code>data/questions/questions.jsonl</code>.
       This is the list of what people actually want to decide — read it before building anything new.
       To stop receiving questions, delete <code>ask.php</code>.</p>
    <?php if ($asked['total'] === 0): ?>
      <p class="note">None yet.</p>
    <?php else: ?>
      <p class="note"><?= (int) $asked['total'] ?> kept.
        <?php foreach ($asked['by_fit'] as $k => $n): ?>
          <code><?= htmlspecialchars((string) $k, ENT_QUOTES) ?></code> <?= (int) $n ?> ·
        <?php endforeach; ?>
        topics:
        <?php foreach ($asked['by_topic'] as $k => $n): ?>
          <code><?= htmlspecialchars((string) $k, ENT_QUOTES) ?></code> <?= (int) $n ?>
        <?php endforeach; ?></p>
      <table>
        <tr><th>Day</th><th>Sorted as</th><th>Business</th><th>Question</th></tr>
        <?php foreach ($asked['rows'] as $row): ?>
          <tr><td><code><?= htmlspecialchars((string) ($row['at'] ?? ''), ENT_QUOTES) ?></code></td>
              <td><?= htmlspecialchars((string) ($row['fit'] ?? '') . ' / ' . (string) ($row['topic'] ?? '-'), ENT_QUOTES) ?></td>
              <td><?= htmlspecialchars(trim((string) ($row['wedge'] ?? '') . ' ' . (string) ($row['variant'] ?? '')), ENT_QUOTES) ?></td>
              <td dir="auto"><?= htmlspecialchars((string) ($row['q'] ?? ''), ENT_QUOTES) ?></td></tr>
        <?php endforeach; ?>
      </table>
    <?php endif; ?>
  </div>

  <div class="card">
    <h2>Usage</h2>
    <table>
      <tr><th>Month</th><th>Calls</th><th>Input tokens</th><th>Output tokens</th></tr>
      <?php foreach (array_slice(array_reverse($usage, true), 0, 6, true) as $m => $row): ?>
        <tr><td><code><?= htmlspecialchars((string) $m, ENT_QUOTES) ?></code></td>
            <td><?= (int) $row['calls'] ?></td>
            <td><?= number_format((int) $row['input_tokens']) ?></td>
            <td><?= number_format((int) $row['output_tokens']) ?></td></tr>
      <?php endforeach; ?>
      <?php if (!$usage): ?><tr><td colspan="4">No calls yet.</td></tr><?php endif; ?>
    </table>
    <p class="note">Counted from what the provider reports. It is a usage record, not a bill — check
       your provider's own dashboard for cost.</p>
  </div>
</div>
</body>
</html>
