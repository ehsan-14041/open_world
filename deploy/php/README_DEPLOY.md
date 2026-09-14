# Running the three comparisons on a PHP host

Three decision products — cafe, shop and salon — all generated on the host: the engine, the
accounting, the 162-point sensitivity sweep and the rendering. No Python on the server, no
database, no build step, no framework.

**PHP 7.1 or newer**, with zlib and json. The floor is deliberately low: arrow functions and
typed properties (both PHP 7.4) are kept out of the bundle on purpose, because shared hosts are
often years behind their control panel's default. If the host is older still, the app says so
in plain language instead of dying with a parse error — `lib/compat.php` is written in PHP
5-era syntax and is the first thing every entry point requires, since PHP parses a whole file
at include time and a check living inside a modern file never gets to run.

Anything before PHP 7.4 has been out of security support for years, so raising the version in
your control panel is worth doing regardless. In DirectAdmin it is usually under *Account
Manager → PHP Version Selector*; in cPanel, *Select PHP Version*.

The generator under `lib/` is wedge-generic: nothing in it knows what a cafe is. Each wedge
arrives as data in `assets/<wedge>.json`, exported from the Python definitions — including the
assumption registry, which is a declarative spec both languages render, so the prose exists
once rather than once per language.

It is verified to produce a **byte-identical** bundle for every wedge: same trajectories, same
metrics, same 162 grid points, same module hash, same shared fingerprint, same engine and
trajectory fingerprints. Run the check yourself:

```bash
python scripts/verify_php_port.py            # all three
python scripts/verify_php_port.py salon      # just one
```

## 1. Build the bundle

```bash
python scripts/build_web_bundle.py --zip
```

You get `dist/wedges_php/` and a zip named after the build, e.g.
`wedges_php_20260826-2214-a1b2c3d.zip`. The name carries the date, the time and the commit, so
two downloads are never confusable — and `-dirty` on the end means it was built from
uncommitted changes.

```
VERSION.txt          which build this is — open it in a browser to check an upload landed
index.php            routes (which wedge), gate, gzip, caching
intake.php           the intake form, built from the chosen wedge's fields
admin.php            maintainer settings — see README_LLM.md
unlock.php           the password screen
config.sample.php    rename to config.php and set the passwords
lib/                 engine.php, cafe.php, report.php, canon.php  — the generator
                     llm.php, i18n.php, assist.php               — the optional LLM layer
assets/              cafe.json, shop.json, salon.json (the three instruments),
                     wedges.json (the chooser), decision_report.html (the report template),
                     chooser.html (the first screen), strings.json (the translatable copy)
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
| `/` | the chooser — "What kind of business do you run?" |
| `/?w=cafe` · `/?w=shop` · `/?w=salon` | that wedge's demo report |
| `/?w=<id>&new=1` | the intake form for that business type |
| `/?w=<id>&lang=fa` | the same report with translated copy, once you have generated a language |
| `/?w=<id>&theme=light` | the projector/print version, for showing on someone else's screen |
| `/admin.php` | maintainer settings (only once `admin_password` is set) |
| `/VERSION.txt` | which build is deployed — a plain file, so it answers even when PHP cannot |
| `/?version` | the same, plus the PHP version the host is actually running |

**After every upload, open `/VERSION.txt` first.** If it does not match the zip you just
uploaded, the files were not replaced — which is a far more common cause of "the fix did not
work" than the fix being wrong.

Posting the form builds a full report for that cafe, in about half a second.

## Server-side generation vs the in-page form

The report has its own "Try your business" form that recomputes everything in the browser.
That one is instant and nothing leaves the page, but it snaps the supplier increase and the
low-margin share to the nearest values in the grid shipped with the page, and says so on
screen.

`?w=<id>&new=1` re-runs the whole sweep on the server for that business's actual figures — so an owner
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

Most of what is under those paths is not a secret — `assets/frozen.json` is the published
model, and `data/cache/` holds pages the visitor is allowed to see anyway — but two things there
do need the rule. A cached report for one cafe should not be reachable by someone who knows only
another cafe's URL (the filename is a hash of the inputs, so it is not guessable), and
`data/contrib/` holds measurements owners chose to share. Those carry no figures about anyone's
business, but they were given to you, not published.

## Measurements owners choose to share

When an owner runs the two-week price test and reports what it said, the page offers — once,
next to the number, with the exact row on screen — to send that measurement. If they accept,
one line is appended to `data/contrib/measurements.jsonl`:

```json
{"at":"2026-09-07","wedge":"cafe","variant":"bakery","e":0.31,"rise":8,"anon":"zz99aa88bb77"}
```

That is the whole row. The date is the day, not the moment. `anon` is a random id the browser
made up, so a second send from the same browser can be recognised rather than counted as a
second business. No revenue, no cash, no order counts, no name, no address, no IP address: none
of those reach the request, and the row is built from a fixed list of fields rather than from
whatever the client posts.

Why bother: the elasticity this product starts from is borrowed from a 2010 study of eating out
in the United States. It is the weakest number in the model and the page says so. Enough real
measurements and it can be replaced with something measured where your customers actually are.

**To not receive any of this, delete `contribute.php`.** The offer disappears from the page —
it is only shown when the endpoint exists — and nothing else changes.

## Questions owners choose to keep

The home screen has a box where an owner can type their own question. What happens to it:

* **Sorting.** If you switch on *Question router* in `admin.php`, the text is sent to the LLM
  provider configured there — after phone numbers, email addresses and web addresses have been
  removed — and the provider says which of the three situations the question is about, or which
  topic it is if none. It returns fields, not prose; every field is checked against this build,
  and the page writes its own sentence from them. No word or figure the owner reads comes from
  the provider. Each question is one call, counted against the monthly cap. With the router off,
  the box says the site does not read questions automatically, and only sends one the owner asks
  to keep.
* **Keeping.** Only if the owner ticks "Keep my question". One line is appended to
  `data/questions/questions.jsonl`:

  ```json
  {"at":"2026-09-10","lang":"fa","q":"…","fit":"exact","topic":"pricing","wedge":"shop","variant":null,"anon":"k3j9x0aa11bb22cc"}
  ```

  The text is kept as written, minus the scrubbing above. The date is the day. `anon` is a
  random id the browser made — a different one from the id a shared measurement carries, so the
  two files cannot be joined. No IP address, no business figures.

Read them in `admin.php`, under *Questions owners asked*. That list is the best evidence you will
have of which question this tool should learn to answer next.

**To not receive questions, delete `ask.php`.** The box disappears from the home screen.

## Decision-sheet links carry the owner's figures

A decision sheet is a link, and the link contains the figures the owner entered — sales,
costs, cash — so that it can be reopened without a database. Anyone who has the link can
read them. The figures sit after the `#` in the link, which browsers do not send to the
server, so opening a sheet does not put them in this host's access logs. The page tells the
owner this next to the "Copy link" button. Links made before this change carried the
figures in `?sheet=`; they still open, but those requests may already be in your logs.

## Things worth knowing

- **A generated report holds the owner's figures.** They are in `data/cache/` on your server
  and inside the HTML the browser receives. Empty the cache when you are done with a customer;
  it is safe to delete at any time.
- **The in-page form posts nothing.** It recomputes client-side from data already in the page.
  You can say that to a cautious owner and it is true.
- **Memory**: building the full grid peaks around 26 MB. A host capped at 16 MB will fail;
  raise `memory_limit`, or set `allow_custom_reports` to false and serve the cached demo.
- **Speed**: about 0.4 s to build any of the three reports, then cached. The Python pipeline takes minutes for
  the same output because it records a full causal trace the report does not use.
- **Fonts** come from Google Fonts; without internet the page falls back to Georgia and the
  system UI font and still reads fine.
- **No outbound calls** unless you switch the LLM on in the admin page. Even then, generating a
  report never calls anything: translation is generated once and cached to disk, and the intake
  assistant only runs when a visitor asks it to.
- **After changing the model or the template**, re-run `python scripts/export_php_assets.py`
  and re-upload `assets/`. Cache keys include both files' timestamps, so stale pages expire by
  themselves.
