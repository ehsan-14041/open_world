# LLM settings

Off by default. With nothing configured, no network call is ever made and the product behaves
exactly as it does without an LLM — the whole comparison is still computed by the engine on
your host.

## Switching it on

1. Set an admin password in `config.php`. Use a different value from the visitor `password`:

   ```php
   'admin_password' => 'something-only-you-know',
   ```

   **Until you set this, `admin.php` returns 404 and cannot be opened at all.** An install you
   forgot to configure cannot leak a settings page.

2. Open `/admin.php`, sign in, and fill in:

   | Field | What it is |
   |---|---|
   | Base URL | anything speaking the OpenAI chat-completions shape, ending before `/chat/completions` — a provider, a gateway, or a local proxy |
   | Model | the model id exactly as your provider names it |
   | API key | stored in `data/settings.json`, `chmod 600`, never sent to a browser |
   | Monthly call cap | a hard stop; calls are refused once it is hit. 0 disables the cap |
   | Max output tokens, Timeout | per call |

3. Press **Run the test**. One very short call proves the key, the URL and the model name all
   work, and tells you what it cost in tokens.

If you would rather the key never sat in a data file, put it in `config.php` instead — the
server executes that file and never serves it:

```php
'llm_api_key'  => '...',
'llm_base_url' => 'https://your-gateway/v1',
'llm_model'    => 'your-model-id',
```

Anything set there wins, and the admin page shows the key as read-only.

## What the model is allowed to do

**It never produces, adjusts or ranks a figure.** The page tells the customer that its numbers
are not produced by a language model, and that has to stay true. Two jobs only:

### Translate the report

Generate a language once from the admin page. It is written to `data/i18n/<code>.json` and
served from disk, so **a visitor's page view never calls the API** — no per-view cost, no
latency, and the owner's report does not depend on a third party being up.

The substitution runs on the **template**, before the data payload is injected. That ordering is
the guarantee: at the moment the copy is replaced, not one figure, ranking, count or fingerprint
exists in the file yet. A test asserts an English page and a translated page carry a
byte-identical payload.

Each string carries its `${...}` placeholders and inline tags. A translation that drops one,
invents one, or changes the markup is **rejected** and that string stays in English — a page in
two languages is a smaller failure than a page with a broken number. The admin page lists what
was rejected and why.

Right-to-left languages get `dir="rtl"` plus a small correction sheet that keeps figures, the
chart and the A/B/C letters left-to-right, so a number never reads backwards.

A translation is a **draft**. Read it before showing it to a customer — especially the hedged
phrases, which the prompt tells the model to preserve but which are exactly what a fluent
translation tends to flatten ("ranks first under current assumptions" must not become "is
best"). You can edit `data/i18n/<code>.json` by hand; the page picks it up immediately.

Use it with `?lang=fa`, and the intake form offers the same languages.

### Read a description into the intake form

Off by default. The owner types "we do about 32,000 a month, roughly 140 orders a day, supplier
just put prices up 40%" and the eight fields are filled in **as a draft they then check**. The
model is a typist, not an analyst: it returns the words it read each figure from, leaves
anything it cannot find empty rather than guessing, and the engine computes from whatever the
owner finally submits.

**This one does send what the visitor types to your provider**, and the form says so plainly
above the box. It is the only part of the product that sends anything anywhere — the eight
figures themselves are calculated on your server, and the report's own in-page form calculates
in the browser. Keep that distinction when you describe it to a cautious owner.

## Cost and privacy

- Translation: roughly `ceil(catalogue / 25)` calls per language, once. About 5 for the current
  catalogue of 101 strings.
- Intake assistant: one call per use.
- The admin page shows calls and tokens per month, from what the provider reports. It is a
  usage record, not a bill — check your provider's dashboard for cost.
- The key is masked wherever it is displayed, redacted out of provider error messages, and
  never written to the usage log.
- Bundles built by `scripts/build_web_bundle.py` deliberately exclude `data/settings.json`,
  `data/i18n/`, `data/llm_usage.json`, `data/cache/` and `config.php`, so a key or a customer's
  figures cannot travel in a zip by accident.

## When the catalogue changes

If you change the report's copy, re-run:

```bash
python scripts/extract_strings.py
```

and regenerate each language. Strings that no longer exist are ignored, and new ones simply
stay in English until you do.
