# beats -- the verbs the home.space stack calls.
#
# services.toml names verbs; it never reimplements one. Everything about how
# beats actually starts lives here and in compose.home.yml, so rewriting the
# compose file changes nothing at the root.
#
# The per-surface justfiles (api/justfile) are untouched and still do what
# they always did for local development.

set dotenv-load := false

compose := "docker compose -f compose.home.yml"

default:
    @just --list

# --- what the stack calls -------------------------------------------------

# Start the stack. Detached, because docker keeps the processes and systemd
# only fires the verb -- `kind = "oneshot"` in services.toml, same shape as
# classophile.
up-detached:
    {{ compose }} up -d --remove-orphans

down:
    {{ compose }} down

# Build the images. The UI build is the slow one (pnpm install + vite build),
# which is why services.toml gives beats a generous start_timeout.
build:
    {{ compose }} build

# More than a port probe: this asks the API, through the same nginx the
# browser uses, whether it can actually answer. A wedged Mongo shows up here
# rather than as a green dot.
health:
    curl -sf http://127.0.0.1:6008/health >/dev/null

logs:
    {{ compose }} logs --tail=200 -f

# Snapshot Mongo into the stack's backup directory. mongodump runs INSIDE the
# db container -- the database is not published on the LAN and there is no
# host mongo client to rely on.
backup dest:
    mkdir -p {{ dest }}
    {{ compose }} exec -T db sh -c 'mongodump --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db beats --archive --gzip' > {{ dest }}/beats-mongo.archive.gz

# Restore a snapshot taken by `just backup`. Not called by the stack -- this
# is the disaster-recovery half, and it is destructive, so it is never wired
# to a timer.
restore archive:
    {{ compose }} exec -T db sh -c 'mongorestore --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --drop --archive --gzip' < {{ archive }}

# --- development ----------------------------------------------------------

# The full cross-surface test sweep, in the order the pre-push hook runs it.
test:
    cd api && uv run --group dev pytest src/ -q
    cd ui && pnpm test
    cd daemon && go test ./...

# Is the home.space identity service reachable, and does beats agree with it?
# The first thing to check when "Continue with home.space" misbehaves.
sso-doctor:
    #!/usr/bin/env bash
    set -uo pipefail
    echo "issuer (host):"
    curl -sf http://127.0.0.1:6007/health || echo "  UNREACHABLE from the host"
    echo
    echo "issuer (from the api container):"
    {{ compose }} exec -T api sh -c 'curl -sf http://host.docker.internal:6007/health' \
        || echo "  UNREACHABLE from the container -- check extra_hosts/host-gateway"
    echo
    echo "beats sso config:"
    curl -sf -H 'Host: beats.home.space' http://127.0.0.1:6008/api/auth/sso/config \
        || echo "  beats not answering on 6008"
