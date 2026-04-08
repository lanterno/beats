#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "==> Installing lefthook"
curl -1sLf 'https://dl.cloudsmith.io/public/evilmartians/lefthook/setup.deb.sh' | sudo -E bash
sudo apt-get install -y lefthook

echo "==> Setting up API"
cd api
uv sync --group dev
cd ..

echo "==> Setting up UI"
cd ui
corepack enable
pnpm install
npx playwright install --with-deps chromium
cd ..

echo "==> Installing git hooks"
lefthook install

echo "==> Ready!"
