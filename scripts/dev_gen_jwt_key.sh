#!/usr/bin/env bash
# Generate a local, gitignored development signing key for Identity.
# Never commit this key; production injects its own via a Docker/Kubernetes secret.
set -euo pipefail

KEY="ops/identity/jwt_private_key.pem"
mkdir -p ops/identity
if [ -f "$KEY" ]; then
  echo "$KEY already exists — leaving it in place"
  exit 0
fi
openssl genrsa -out "$KEY" 2048
chmod 600 "$KEY"
echo "generated $KEY (gitignored) — restart the backend to load it"
