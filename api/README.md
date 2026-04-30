# Beats API

Because life is a time-series of heart beats.

Measures the whole time spent on every project you have and helps you manage time on your projects.

Goal: To become your time-aware assistant. *To record even your heart beats.*

See `CLAUDE.md` for the architecture, runtime, and testing conventions, and the repo-root `README.md` for the broader system overview.

## Open Roadmap

- [ ] Per-environment databases (dev / staging / prod isolation)

API, Artifact Registry, and the MongoDB Atlas cluster all live in
`europe-west1` (Belgium) on GCP — already intra-region with each other,
so API↔DB latency is ~2 ms and the Eurozone proximity item is closed.

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

Pushes to `main` trigger Google Cloud Build, which builds the Docker image, pushes it to Artifact Registry, and runs `terraform apply` to deploy to Cloud Run.
