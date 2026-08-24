# Putting the report on a PHP host

The report is a **self-contained static page** — one HTML file with the model output, the
styling and the interactivity already inside it. It needs no database, no framework and no
build step on the server. PHP is used for exactly two things:

- **gzip** — the page is about 1 MB and compresses to about 78 KB, which matters on a phone;
- **a shared password** — so a pre-customer demo isn't sitting on the open web.

If you want neither, you can ignore this folder entirely and upload
`reports/<cafe>/cafe_decision_report.html` as a plain `.html` file. It will work.

Requirements: PHP 7.4+ with zlib (every shared host has both).

## 1. Build the bundle

```bash
python scripts/build_web_bundle.py --zip
```

For a real cafe's report:

```bash
python scripts/build_web_bundle.py --report reports/corner_bean --zip
```

You get `dist/<name>_web/` and `dist/<name>_web.zip`:

```
index.php            entry point — gate, gzip, headers
unlock.php           the password screen
config.sample.php    rename to config.php and set the password
data/report-XXXX.html.gz   the report (random name, see "How private is it")
.htaccess            Apache: blocks direct access to data/
robots.txt           keeps it out of search engines
```

## 2. Upload

Upload the **contents** of the folder (or unzip the `.zip`) into your web root —
`public_html/`, or a subfolder like `public_html/decision/` for a nicer URL.

## 3. Set the password

Rename `config.sample.php` to `config.php` and edit one line:

```php
'password' => 'whatever-you-give-the-owner',
```

Leave `'password' => ''` to make the page public. `heading` is the title on the password
screen — the cafe's name works well here.

You can also bake it in at build time, but the password then lands in your shell history:

```bash
python scripts/build_web_bundle.py --password 'cafe-demo' --heading 'Corner Bean' --zip
```

Add `?logout=1` to the URL to clear your own session while testing.

## 4. Open it

`https://yourdomain.com/decision/` — that's all. Add `?theme=light` for the projector/print
version, which is what to use when showing it on someone else's screen.

## How private is it

The password is a **shared secret for a demo**, not authentication: no accounts, no rate
limiting, no lockout. It keeps the page off the open web and out of search results. Don't put
a real customer's financial figures behind it and consider them protected — for that, send the
file directly instead.

The report file inside `data/` gets a random name at build time. That's deliberate: `.htaccess`
protects it on Apache and LiteSpeed, but **nginx and Caddy ignore `.htaccess` entirely**, and
on those a predictable path like `data/report.html.gz` would let anyone walk straight around the
password. The random name closes that on every server. So: don't rename the file, don't link to
it directly, and if you're on nginx and want belt-and-braces, add:

```nginx
location ^~ /decision/data/ { deny all; }
```

## Things worth knowing

- **The owner's numbers never leave their browser.** The "Try your business" form recomputes
  everything client-side from data already in the page. Nothing is posted anywhere, and there
  is no logging to switch on. You can say this to a cautious owner and it is true.
- **Fonts come from Google Fonts.** With no internet the page falls back to Georgia and the
  system UI font and still reads fine. To remove the dependency entirely you would need to
  self-host the two families — not worth doing before a paying customer.
- **`Cache-Control` differs by mode**: `no-store` when a password is set, five minutes of
  public caching when it isn't.
- **Double compression**: if the host forces its own gzip (`zlib.output_compression`), the page
  detects it and serves uncompressed rather than sending a corrupted body.
- **To update the report**, rebuild and re-upload `data/` — but delete the old
  `report-*.html.gz` first; `index.php` takes the first match and two files there is ambiguous.
