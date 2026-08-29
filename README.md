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

`CNAME` in this repo sets the custom domain. Add a DNS record on `djr.li`:

```
vinewoodvault  CNAME  rymand.github.io.
```

## Legal pages

`privacy.html` and `terms.html` are drafts written for this app's actual
behaviour (no accounts, no analytics, local-only progress, StoreKit purchases).
Have them reviewed before the App Store submission and set the effective date /
governing-law jurisdiction.
