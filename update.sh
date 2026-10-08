#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec python3 deploy.py --file "${1:-deployment/compose.json}" update
