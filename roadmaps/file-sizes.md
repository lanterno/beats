# Files past the size ceiling

**The rule, stated 2026-11-06: a Python file above 1000 lines is too big; a
frontend file above 5000 is.** We prefer a clean, well-structured but not very
deep tree — so the fix is carving at existing seams, never adding layers.

No frontend file is anywhere near its ceiling (the largest TS/Dart/Go files
sit under 3000). The Python files over 1000, measured 2026-11-06, newest
offenders first fixed already (`test_operator.py` split; the account-control
classes left `test_api.py`):

| File | Lines | The seams to carve at |
|---|---|---|
| `api/src/test_api.py` | ~10 950 | One class per router already — split **by router area**, the way `test_organisations.py` and `test_account_controls.py` already stand apart: projects+timer, beats, billing+clients+reports (these share the module's billing helpers, which move to a non-`test_`-prefixed helpers module beside `conftest.py`), devices+signals, coach, integrations, export/import, SSO. Mechanical but wide; the helpers move is the one real decision |
| `api/src/beats/test_domain.py` | ~5 900 | By the domain module under test: analytics, intelligence, models/validation, timer — mirroring how contracts/ledger/vacation/billing already have files of their own |
| `api/src/beats/test_coach.py` | ~4 280 | By surface: gateway+usage, chat loop, briefs, memory/context |
| `api/src/test_organisations.py` | ~3 120 | Stage seam: the organisations contract vs employment (stages 3–4 — managed contracts, requests, timesheets, teams, audit); the wall test stays with the contract |
| `api/src/beats/domain/models.py` | 1 968 | The one models file is deliberate (every import site names it), but it has clean sections: organisations models (~500 lines) and billing models could each move to `models_organisations.py` / `models_billing.py` re-exported from `models.py`, keeping import sites working. Decide whether the re-export indirection is worth it before cutting |
| `api/src/beats/infrastructure/repositories.py` | 1 586 | `MongoStore` + serializers stay; the billing repositories (clients, project billing, overrides, budgets, report links) are a cohesive ~500-line block for a `billing_repositories.py`, as `organisations.py` already stands apart |
| `api/src/beats/domain/organisations.py` | 1 360 | The closing/deletion block and the operator twins (~250 lines) could follow `employment.py`'s pattern — a service extending the base — but the twins were put beside the methods they twin on purpose; weigh that against the ceiling |
| `api/src/beats/test_auth.py` | 1 342 | SessionManager vs WebAuthnManager halves |
| `api/src/beats/domain/services.py` | 1 313 | `ContractService` (~420 lines) to `contract_service.py`, beside the `contracts.py` arithmetic it reads |
| `api/src/beats/infrastructure/organisations.py` | 1 202 | `MongoOrganisationStore` vs `MongoOrganisationRecords` — the two classes are already independent; one file each |
| `api/src/beats/api/schemas.py` | 1 009 | Barely over; the billing/report response models are the block to move if it keeps growing |

Each split is its own change (a refactor commit, imports rewritten, no
behaviour moved), small enough to review in one sitting; `test_api.py`'s is
the only one needing a decision first — where its shared billing helpers
live. None blocks anything else.
