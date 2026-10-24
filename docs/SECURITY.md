# Security and static-scan evidence

This is the final scan of the **submission zip**, extracted into a clean staging
directory (not the working tree). Commands are in `tools/scan.sh`.

## Result

| Check | Tool | Result |
|---|---|---|
| SAST | OpenGrep 1.31.0, `--config=r/all` | **0 ERROR / 0 WARNING**, 5 INFO |
| Vulnerabilities | Trivy 0.76.0, `vuln` | **0** |
| Secrets | Trivy 0.76.0, `secret` | **0** |
| Licences | Trivy 0.76.0, `license` | **0** (no third-party runtime packages) |
| Misconfiguration | Trivy 0.76.0, `misconfig` | Scanner hangs in this WSL installation; manual checklist below |

The 5 INFO findings are non-failing: the base image tag is not pinned by digest
(no Docker daemon available to resolve one), the generic AI-provider rule, and
three test asserts in `tools/make_zip.py`. No ERROR or WARNING remains.

## Real issues found and fixed

- **API path surface** — `web/js/api.js` now allows only same-origin `/api/*`
  paths and blocks cross-origin targets before `fetch`.
- **XSS surface** — removed the unused `innerHTML` prop from the DOM helper;
  all dynamic text uses `textContent`.
- **XXE** — AIDX parsing rejects `<!DOCTYPE>` and `<!ENTITY>` before
  `ElementTree.fromstring`, and enforces a 2 MB message cap. The scanner's
  stdlib-XML rule is suppressed at those exact lines with that reason.
- **Dynamic SQL** — table/column names come only from closed whitelists;
  values are always bound. Suppression comments are scoped to those three
  statements with the whitelist reason.
- **Legacy browser API** — `replaceAll` replaced with `String.replace(/…/g)`
  for the target browsers.

## Documented false-positive exclusions

`tools/scan.sh` lists each excluded rule and why. The main ones are:
OpenGrep's `return-not-in-function` (valid returns inside dataclass
`default_factory` lambdas), `detect-object-injection` (internal map lookups only),
`missing-template-string-indicator` (valid template literals),
dynamic i18n key format, timing-attack rules on non-secret UI state, console
error disclosure in a local handler, and the compose port rule for the LAN QR
flow. These are scanner limitations, not suppressed code defects; the exclusion
list is visible and reviewable.

## Manual misconfiguration checklist

- Dockerfile runs as non-root `meridian` (UID/GID 10001), has a JSON
  `HEALTHCHECK`, no build secrets, no package installs.
- Compose publishes 8000 deliberately for the LAN QR claim page; database is
  in a named volume; app data is writable only where needed.
- No `.env`, real token, API key, private key, `__pycache__`, `*.pyc`, `*.db`,
  log or runtime artifact is inside the submission zip.
- CSP is self-only (scripts, fonts, images; `data:` for generated QR), with
  `X-Content-Type-Options`, frame/referrer/permissions headers.
- The only external runtime dependency is none: Python 3.11 standard library
  and vanilla ES modules.
