# Running the comparison on a PHP host

Everything runs on the host: the engine, the accounting, the 162-point sensitivity sweep and
the rendering. No Python on the server, no database, no build step, no framework. PHP 7.4+
with zlib and json — every shared host has both.

The generator under `lib/` is a port of the Python pipeline. It is verified to produce a
**byte-identical** bundle: same trajectories, same metrics, same 162 grid points, same module
hash, same shared fingerprint, same three engine fingerprints. Run the check yourself:

```bash
python scripts/verify_php_port.py
```

## 1. Build the bundle

```bash
python scripts/build_web_bundle.py --zip
```

You get `dist/cafe_php/` and a `.zip`:

```
index.php            routes, gate, gzip, caching
intake.php           the eight-field form
admin.php            maintainer settings — see README_LLM.md
unlock.php           the password screen
config.sample.php    rename to config.php and set the passwords
lib/                 engine.php, cafe.php, report.php, canon.php  — the generator
                     llm.php, i18n.php, assist.php               — the optional LLM layer
assets/              frozen.json (the instrument), decision_report.html (the template),
                     strings.json (the translatable copy)
data/cache/          generated pages, keyed by a hash of the inputs (safe to delete)
data/settings.json   written by admin.php; holds the API key if you set one there
data/i18n/           generated translations
.htaccess            Apache: blocks direct access to lib/, assets/ and data/
robots.txt           keeps it out of search engines
```

## 2. Upload

Upload the contents into your web root — `public_html/`, or a subfolder like
`public_html/decision/` for a nicer URL. Make `data/cache/` writable (755 or 775) if you can;
if you cannot, the app still works, it just rebuilds each page instead of caching it.

## 3. Set the password

Rename `config.sample.php` to `config.php`:

```php
'password' => 'whatever-you-give-the-owner',
'allow_custom_reports' => true,
```

Leave `'password' => ''` to make the page public. Set `allow_custom_reports` to `false` to
serve only the demo and hide the intake form. `?logout=1` clears your own session.

To reach the settings page, also set a **different** `admin_password`. Until you do, `admin.php`
returns 404. Everything it configures is optional — see [README_LLM.md](README_LLM.md).

## 4. The URLs

| URL | What it does |
|---|---|
| `/` | the demo cafe |
| `/?new=1` | the intake form — eight figures |
| `/?lang=fa` | the same report with translated copy, once you have generated a language |
| `/?theme=light` | the projector/print version, for showing on someone else's screen |
| `/admin.php` | maintainer settings (only once `admin_password` is set) |

Posting the form builds a full report for that cafe, in about half a second.

## Server-side generation vs the in-page form

The report has its own "Try your business" form that recomputes everything in the browser.
That one is instant and nothing leaves the page, but it snaps the supplier increase and the
low-margin share to the nearest values in the grid shipped with the page, and says so on
screen.

`?new=1` re-runs the whole sweep on the server for that cafe's actual figures — so an owner
with 30% of orders on low-margin items gets a grid built on 4.5 / 9 / 13.5 points of
ingredient-cost saving instead of the demo's 3 / 6 / 9. Use the in-page form in the room; use
`?new=1` for the report you send afterwards.

## How private is it

The password is a **shared secret for a demo**, not authentication: no accounts, no rate
limiting, no lockout. It keeps the page off the open web and out of search results. For a real
customer's financial figures, send the file directly instead.

`.htaccess` blocks `lib/`, `assets/` and `data/` on Apache and LiteSpeed. **nginx and Caddy
ignore `.htaccess` entirely**, so on those add:

```nginx
location ~ ^/decision/(lib|assets|data)/ { deny all; }
```

Nothing under those paths is a secret — `assets/frozen.json` is the published model, and
`data/cache/` holds pages the visitor is allowed to see anyway — but a cached report for one
cafe should not be reachable by someone who knows only another cafe's URL. The cache filename
is a hash of the inputs, so it is not guessable.

## Things worth knowing

- **A generated report holds the owner's figures.** They are in `data/cache/` on your server
  and inside the HTML the browser receives. Empty the cache when you are done with a customer;
  it is safe to delete at any time.
- **The in-page form posts nothing.** It recomputes client-side from data already in the page.
  You can say that to a cautious owner and it is true.
- **Memory**: building the full grid peaks around 26 MB. A host capped at 16 MB will fail;
  raise `memory_limit`, or set `allow_custom_reports` to false and serve the cached demo.
- **Speed**: about 0.4 s to build a report, then cached. The Python pipeline takes minutes for
  the same output because it records a full causal trace the report does not use.
- **Fonts** come from Google Fonts; without internet the page falls back to Georgia and the
  system UI font and still reads fine.
- **No outbound calls** unless you switch the LLM on in the admin page. Even then, generating a
  report never calls anything: translation is generated once and cached to disk, and the intake
  assistant only runs when a visitor asks it to.
- **After changing the model or the template**, re-run `python scripts/export_php_assets.py`
  and re-upload `assets/`. Cache keys include both files' timestamps, so stale pages expire by
  themselves.
