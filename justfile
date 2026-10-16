# LifePete's root verbs: the self-hosted stack (compose.selfhost.yml) and the
# cross-surface test sweep. The per-surface justfiles (api/justfile) are
# untouched and still do what they always did for local development.

set dotenv-load := false

compose := "docker compose -f compose.selfhost.yml"

default:
    @just --list

# --- the self-hosted stack -----------------------------------------------

# Start the stack, detached: docker keeps the processes running.
up-detached:
    {{ compose }} up -d --remove-orphans

down:
    {{ compose }} down

# Build the images. The UI build is the slow one (pnpm install + vite build).
build:
    {{ compose }} build

# More than a port probe: this asks the API, through the same nginx the
# browser uses, whether it can actually answer. A wedged Mongo shows up here
# rather than as a green dot.
health:
    curl -sf http://127.0.0.1:6008/health >/dev/null

logs:
    {{ compose }} logs --tail=200 -f

# Snapshot Mongo into a backup directory. mongodump runs INSIDE the db
# container -- the database is not published outside the stack and there is
# no host mongo client to rely on.
backup dest:
    mkdir -p {{ dest }}
    {{ compose }} exec -T db sh -c 'mongodump --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db beats --archive --gzip' > {{ dest }}/beats-mongo.archive.gz

# Restore a snapshot taken by `just backup`. Destructive: it drops what is
# there first, so it is never wired to a timer.
restore archive:
    {{ compose }} exec -T db sh -c 'mongorestore --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --drop --archive --gzip' < {{ archive }}

# --- development ----------------------------------------------------------

# The full cross-surface test sweep, in the order the pre-push hook runs it.
test:
    cd api && uv run --group dev pytest src/ -q
    cd ui && pnpm test
    cd daemon && go test ./...
