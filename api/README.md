# Beats API

Because life is a time-series of heart beats.

Measures the whole time spent on every project you have and helps you manage time on your projects.

Goal: To become your time-aware assistant. *To record even your heart beats.*

See `CLAUDE.md` for the architecture, runtime, and testing conventions, and the repo-root `README.md` for the broader system overview.

## Open Roadmap

- [ ] Provide meaningful errors at the API surface (consistent shape, codes, fielded validation messages)
- [ ] Per-environment databases (dev / staging / prod isolation)
- [ ] Move Cloud Run region closer to the user (Eurozone) to reduce round-trip latency

### Database

MongoDB hosted in the cloud.

### Deployment

Pushes to `main` trigger Google Cloud Build, which builds the Docker image, pushes it to Artifact Registry, and runs `terraform apply` to deploy to Cloud Run.
