# Beats API

Because life is a time-series of heart beats.

Measures the whole time spent on every project you have and helps you manage time on your projects.

Goal: To become your time-aware assistant. *To record even your heart beats.*

See `CLAUDE.md` for the architecture, runtime, and testing conventions, and the repo-root `README.md` for the broader system overview.

## Infrastructure

The API runs in **two** live deployments — see the repo-root `CLAUDE.md`
before changing anything either one depends on:

- **home.space** — `compose.home.yml`, behind one nginx that also serves
  the SPA. Same origin, so CORS is not involved.
- **lifepete.com** — Cloud Run at `api.lifepete.com`, with the SPA on
  Firebase Hosting at `lifepete.com`. Two origins, joined by CORS; both
  are listed in `origins` in `src/server.py`.

For the Cloud Run deployment, the API, Artifact Registry and the MongoDB
Atlas cluster all live in `europe-west1` (Belgium) — already
intra-region, so API↔DB latency is ~2 ms.

Local dev uses the `db` service in `compose.yml` (`mongo:8`, isolated
from prod). Tests use `testcontainers` (ephemeral). Atlas only sees
production traffic.

## Error Shape

Every HTTP error from the API uses the unified envelope defined in
`beats.api.errors`:

```json
{
  "detail": "<human-readable message>",
  "code": "<MACHINE_READABLE_CODE>",
  "fields": [
    {"path": "project_id", "message": "Field required", "type": "missing"}
  ]
}
```

`fields` only appears on `422 VALIDATION_ERROR` responses; routers can
override `code` by raising `HTTPException(detail={"code": "X", "message": "..."})`.

### Database

MongoDB hosted in the cloud.

### Deployment

Pushes to `main` trigger Google Cloud Build, which builds the Docker image, pushes it to Artifact Registry, and runs `terraform apply` to deploy to Cloud Run. The SPA half of that deployment ships separately, from the `deploy` job in `.github/workflows/ui.yml` — so the two can skew, and an older SPA against a newer API is a real state to reason about.
