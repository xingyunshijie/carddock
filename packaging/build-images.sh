#!/bin/sh
# Build both architectures without uploading anything to a registry.
set -eu
cd "$(dirname "$0")/.."
mkdir -p dist
for arch in amd64 arm64; do
  docker buildx build --platform "linux/$arch" --tag "carddock:0.12.0-beta.1-$arch" \
    --output "type=docker,dest=dist/carddock-0.12.0-beta.1-$arch.tar" .
done
