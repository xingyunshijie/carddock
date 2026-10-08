#!/bin/sh
# Explicit user-invoked publication; no credentials are stored here.
set -eu
[ "$#" = 1 ] || { echo 'Usage: sh packaging/publish-images.sh registry/owner/carddock:0.12.0-beta.1' >&2; exit 1; }
cd "$(dirname "$0")/.."
docker buildx build --platform linux/amd64,linux/arm64 --tag "$1" --push .
