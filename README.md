# vinewoodvault.djr.li

Static site for the Vinewood Vault app: landing page, privacy policy, terms of
use, support. Served by GitHub Pages at **https://vinewoodvault.djr.li**.

Plain HTML, no build step (`.nojekyll`). Each page is a flat file that GitHub
Pages also serves without the `.html` extension, so:

| File | URL |
|---|---|
| `index.html` | `/` |
| `privacy.html` | `/privacy` |
| `terms.html` | `/terms` |
| `support.html` | `/support` |

The app links to `/privacy` and `/terms` from the paywall.

## DNS

`CNAME` in this repo sets the custom domain. Add a DNS record on the `djr.li`
zone pointing at the GitHub Pages user host for the account that owns this repo:

```
vinewoodvault  CNAME  dannyryman19.github.io.
```

## Legal pages

`privacy.html` and `terms.html` are written for this app's actual behaviour
(no accounts, no analytics, local-only progress, StoreKit purchases). Draft
banners removed, "Last updated" set to 2026-08-31, governing law set to
England and Wales. The subscription section in `terms.html` covers the
App Store auto-renewal disclosures (billing period, auto-renew, how to
cancel, prices shown at point of purchase, Apple Standard EULA link).
Update the date and governing law if either changes; a legal review is still
worth doing but nothing here blocks submission.
