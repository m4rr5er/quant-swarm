#!/usr/bin/env bash
# Download nats-server into deploy/bin/ (Linux/WSL). Binaries are gitignored.
set -euo pipefail

VERSION="${1:-v2.15.3}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/deploy/bin"
mkdir -p "$DEST"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSL "https://github.com/nats-io/nats-server/releases/download/${VERSION}/nats-server-${VERSION}-linux-amd64.tar.gz" -o "$TMP/nats.tgz"
tar xzf "$TMP/nats.tgz" -C "$TMP"
cp "$TMP/nats-server-${VERSION}-linux-amd64/nats-server" "$DEST/nats-server"
chmod +x "$DEST/nats-server"
echo "nats-server ${VERSION} -> $DEST/nats-server"
