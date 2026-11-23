#!/bin/bash
# Download Geist font files via local proxy (usage: bash scripts/fetch_fonts.sh)
set -e
export HTTPS_PROXY=http://172.24.192.1:7897 HTTP_PROXY=http://172.24.192.1:7897
D=/mnt/c/projects/devin_projects/quant-swarm/src/quant_swarm/uiweb/static/vendor/fonts
base=https://cdn.jsdelivr.net/npm/@fontsource
for w in 400 500 600 700; do
  curl -sfL "$base/geist-sans@5.2.5/files/geist-sans-latin-${w}-normal.woff2" -o "$D/geist-sans-${w}.woff2"
done
for w in 400 500; do
  curl -sfL "$base/geist-mono@5.2.5/files/geist-mono-latin-${w}-normal.woff2" -o "$D/geist-mono-${w}.woff2"
done
ls -la "$D" | grep geist
