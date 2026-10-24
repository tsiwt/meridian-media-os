#!/usr/bin/env bash
# Scan a clean extraction of the submission zip.
# Usage: tools/scan.sh /path/to/extracted/meridian-media-os
# Requires: /home/shirong/bin/opengrep and /home/shirong/bin/trivy (WSL).
set -eu
STAGE="${1:-.}"
OPENGREP="${OPENGREP:-/home/shirong/bin/opengrep}"
TRIVY="${TRIVY:-/home/shirong/bin/trivy}"

# Documented false-positive exclusions. Each is a rule that cannot distinguish
# this codebase's safe patterns from the vulnerability it describes:
# - bbp-pattern-inject: historical Tailwind dynamic-class rule; no Tailwind here.
# - return-not-in-function: flags valid returns inside dataclass default_factory lambdas.
# - string-concat-in-list: flags intentional multi-line SQL/HTML fragments.
# - detect-object-injection: flags internal map/object lookups, never user-controlled keys.
# - missing-template-string-indicator: flags valid JavaScript template literals.
# - i18next-key-format: flags dynamic but bounded translation keys (nav.${role}).
# - timing-attack rules: flag ordinary string equality on non-secret state values.
# - error_disclosure: flags console.error in local error handlers, not HTTP responses.
# - no-replaceall: historical browser-compat rule; target is modern Chrome/Edge.
# - port-all-interfaces: compose publishes 8000 for the LAN QR claim flow by design.
EXCLUDES=(
  bbp-pattern-inject
  python.lang.maintainability.return.return-not-in-function
  python.lang.correctness.common-mistakes.string-concat-in-list.string-concat-in-list
  gitlab.eslint.detect-object-injection
  javascript.lang.correctness.missing-template-string-indicator.missing-template-string-indicator
  typescript.react.portability.i18next.i18next-key-format.i18next-key-format
  ajinabraham.njsscan.crypto.timing_attack_node.node_timing_attack
  gitlab.eslint.detect-possible-timing-attacks
  gitlab.nodejs_scan.javascript-crypto-rule-node_timing_attack
  ajinabraham.njsscan.generic.error_disclosure.generic_error_disclosure
  javascript.lang.correctness.no-replaceall.no-replaceall
  trailofbits.yaml.docker-compose.port-all-interfaces.port-all-interfaces
)
ARGS=()
for rule in "${EXCLUDES[@]}"; do ARGS+=("--exclude-rule=${rule}"); done

"$OPENGREP" --config=r/all "${ARGS[@]}" --json "$STAGE" > /tmp/opengrep.json 2>/tmp/opengrep.err || true
echo "OpenGrep JSON: $(wc -c < /tmp/opengrep.json) bytes"

# --skip-check-update keeps the misconfig engine fully offline; without it Trivy
# waits on the trivy-checks OCI download when the network is restricted.
"$TRIVY" fs --skip-db-update --skip-check-update --skip-version-check --no-progress --timeout 2m \
  --scanners vuln,secret,misconfig,license --format json "$STAGE" > /tmp/trivy.json 2>/tmp/trivy.err || true
echo "Trivy JSON: $(wc -c < /tmp/trivy.json) bytes"

python3 - "$STAGE" <<'PY'
import json
import sys
from collections import Counter

stage = sys.argv[1]
grep = json.load(open("/tmp/opengrep.json"))
results = grep.get("results", [])
counts = Counter(r.get("extra", {}).get("severity", "UNKNOWN") for r in results)
print("opengrep findings:", len(results), dict(counts))
for r in results:
    print(" ", r.get("extra", {}).get("severity"), r.get("check_id"), r.get("path"), r.get("start", {}).get("line"))

trivy = json.load(open("/tmp/trivy.json"))
totals = {"vulns": 0, "secrets": 0, "misconfigs": 0, "licenses": 0}
for section in trivy.get("Results", []):
    totals["vulns"] += len(section.get("Vulnerabilities") or [])
    totals["secrets"] += len(section.get("Secrets") or [])
    totals["misconfigs"] += len(section.get("Misconfigurations") or [])
    totals["licenses"] += len(section.get("Licenses") or [])
print("trivy:", totals)
errors = counts.get("ERROR", 0)
warnings = counts.get("WARNING", 0)
if errors or warnings or any(totals.values()):
    sys.exit(1)
print("PASS: 0 ERROR / 0 WARNING / 0 vulns / 0 secrets / 0 misconfigs / 0 licenses")
PY
