<?php
/**
 * Maintainer settings.
 *
 * Reachable only when `admin_password` is set in config.php — with no admin password this page
 * refuses to load at all, so an unconfigured install cannot expose it. The session is separate
 * from the visitor gate: unlocking the report does not unlock this.
 */
declare(strict_types=1);

require_once __DIR__ . '/lib/llm.php';
require_once __DIR__ . '/lib/i18n.php';

$config = is_file(__DIR__ . '/config.php') ? (require __DIR__ . '/config.php') : [];
$adminPassword = (string) ($config['admin_password'] ?? '');

if ($adminPassword === '') {
    http_response_code(404);
    header('Content-Type: text/plain; charset=utf-8');
    exit("The admin page is off.\n\nSet 'admin_password' in config.php to switch it on.");
}

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
