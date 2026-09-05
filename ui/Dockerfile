# The SPA, built once and served by nginx — for the home.space deployment.
#
# Beats used to ship this bundle to Firebase Hosting and the API to Cloud Run,
# on two different origins joined by CORS. Here they share ONE origin: this
# nginx serves the bundle at `/` and proxies `/api` to the API container
# behind it. That is not a packaging preference — the `Home-Session` cookie
# the home.space identity service mints is what carries SSO, and a browser
# only attaches it to same-origin requests. Split the origins again and SSO
# stops working.

FROM node:25-alpine AS build

WORKDIR /app

# Node 25 no longer bundles corepack, so it is installed rather than enabled.
# Still corepack and not a pinned `npm i -g pnpm@x`, because corepack reads the
# `packageManager` field in package.json — which keeps the pnpm version here in
# lockstep with the one developers use, from one source of truth.
# --force because the image already ships a `yarn` shim that corepack also
# wants to own; without it npm refuses the install over that one file.
RUN npm install -g --force corepack@latest && corepack enable

# Dependencies first, so a source-only change doesn't refetch the world.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

# No VITE_API_URL is set on purpose. A production build with none configured
# resolves the API to the SAME ORIGIN (see `client/shared/config/index.ts`),
# which is exactly what this image serves. `.env` is in .dockerignore, so the
# repo's `VITE_API_URL=http://localhost:7999` cannot leak in here either.
RUN pnpm build

# Prove it. A bundle that still names localhost:7999 would fail silently at
# runtime — every API call from a phone would hit the phone's own port 7999,
# and SSO would break invisibly because the cookie is only sent same-origin.
# `import.meta.env.DEV` is a build-time literal, so the dev branch really is
# eliminated and this grep means what it says.
RUN if grep -rq "localhost:7999" dist/spa/assets/; then \
      echo "BUILD ERROR: bundle still targets localhost:7999 — it must use the page origin" >&2; \
      exit 1; \
    fi

FROM nginx:1.29-alpine

COPY --from=build /app/dist/spa /usr/share/nginx/html
COPY nginx.home.conf /etc/nginx/conf.d/default.conf

# 6008 inside the container as well as outside, so the published mapping is a
# plain 6008:6008 and `http://localhost:6008` means the same thing in both
# places — the same correction classophile's UI needed when it joined the stack.
EXPOSE 6008
