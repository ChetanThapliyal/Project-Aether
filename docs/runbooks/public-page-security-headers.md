# Public page security headers

> **Scope:** the response headers on `status.chetan-thapliyal.cloud` (Glance on the GCP DMZ, served through the Cloudflare tunnel).
> **Status:** Operational runbook
> **Source of truth:** [`cloudflare-response-headers.yml`](../../infrastructure/docker/gcp-dmz/cloudflare-response-headers.yml)
> **Check:** [`check_public_headers.py`](../../infrastructure/ansible/templates/check_public_headers.py), run by `task ansible:dmz`

## Why it is done this way

Glance can't set response headers, and the Cloudflare zone isn't managed in Terraform. The headers are set by a single Cloudflare **Response Header Transform Rule**, added by hand from the values in the YAML file. Every DMZ deploy compares the live page with that file, so the dashboard and the repository can't drift apart without the deploy failing.

The Content-Security-Policy allows scripts only from the site itself plus one hash per page and theme. Glance renders a short inline script on each page that differs only by the page slug and the theme key (from the visitor's `theme` cookie: `default` for Auto, `default-dark`, `default-light`), so there are fifteen hashes: five pages times three themes. The check fetches every page once per theme with that cookie. Styles allow `'unsafe-inline'`, because Glance writes its theme into an inline `<style>` block. Glance escapes every value it renders, so allowing inline styles doesn't open a script path.

## 1. Print the values

```bash
python3 infrastructure/ansible/templates/check_public_headers.py \
  --config infrastructure/docker/gcp-dmz/cloudflare-response-headers.yml --print-rule
```

This prints each header name and its exact value, with the hashes already filled into the CSP.

## 2. Add or update the Cloudflare rule

1. Open the zone in the Cloudflare dashboard, then go to **Rules → Overview → Create rule → Response Header Transform Rule**. If the rule already exists, edit **Public page security headers** instead.
2. Name: `Public page security headers`.
3. Under "If incoming requests match", choose **Custom filter expression**: `Hostname` `equals` `status.chetan-thapliyal.cloud`.
4. For each header printed in step 1, add **Set static** with that header name and value. Paste each value whole. A CSP value that is cut short blocks the page.
5. Deploy the rule.

## 3. Verify

```bash
task ansible:dmz -- --tags headers
```

The check should print `OK: script hashes match; live headers equal the file`. Then:

- Open the page in a browser with the console open, and visit each tab. In `report-only` mode, a problem appears as a console message that starts with `[Report Only]`.
- Run the page through securityheaders.com. The target is grade A or better.

## 4. Switch from report-only to enforcing

Start in `report-only` mode (`csp_mode: report-only`). The browser reports violations but blocks nothing. After a few days with a clean console on every tab:

1. Set `csp_mode: enforce` in the YAML and commit.
2. Print the values again (step 1). In the Cloudflare rule, delete `Content-Security-Policy-Report-Only` and add `Content-Security-Policy` with the same value.
3. Run the check (step 3).

## When a Glance upgrade fails the deploy

A Glance version bump can change the inline script, and the deploy then stops with `MISMATCH /<page> (theme <key>): inline script hash sha256-... != csp_script_hashes.<key>.<page>`.

1. Put the printed hashes in `csp_script_hashes`, one per page under each theme.
2. Commit, print the values (step 1) and update the CSP value in the Cloudflare rule.
3. Rerun the check.

The same applies when a page is added to `glance.yml`: it needs a hash entry under its slug in every theme. Adding a theme preset adds a block of five.
