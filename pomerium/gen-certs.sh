#!/usr/bin/env bash
# Generate a self-signed wildcard cert for the local *.localhost.pomerium.io
# demo domains. Output lands in pomerium/certs/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p certs

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/localhost.pomerium.io.key \
  -out certs/localhost.pomerium.io.crt \
  -days 365 \
  -subj "/CN=*.localhost.pomerium.io" \
  -addext "subjectAltName=DNS:*.localhost.pomerium.io,DNS:localhost.pomerium.io"

echo "Wrote certs/localhost.pomerium.io.{crt,key}"
