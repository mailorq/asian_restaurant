#!/usr/bin/env bash
# CI guard: reject PEM / private-key material in tracked files. Wire into CI as required.
set -euo pipefail

fail=0

# tracked key files by extension
keyfiles=$(git ls-files -- '*.pem' '*.key' '*.p12' '*.pfx' || true)
if [ -n "$keyfiles" ]; then
  echo "FAIL: tracked key files:"; echo "$keyfiles"; fail=1
fi

# private-key headers anywhere in tracked content
hdr=$(git grep -lI -E 'BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY' -- . ':(exclude)scripts/check_no_secrets.sh' 2>/dev/null || true)
if [ -n "$hdr" ]; then
  echo "FAIL: private-key material in tracked files:"; echo "$hdr"; fail=1
fi

[ "$fail" -eq 0 ] && echo "no tracked secrets"
exit "$fail"
