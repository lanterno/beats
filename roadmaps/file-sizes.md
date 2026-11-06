# Files past the size ceiling

**The rule, stated 2026-11-06: a Python file above 1000 lines is too big; a
frontend file above 5000 is.** We prefer a clean, well-structured but not very
deep tree — so the fix is carving at existing seams, never adding layers.

No frontend file is anywhere near its ceiling (the largest TS/Dart/Go files
sit under 3000).

The Python files over 1000 were carved on 2026-11-06. What was done, and the
decisions each carve settled:

| Was | Became |
|---|---|
| `api/src/test_api.py` (~10 950) | One file per router area (`test_api_projects`, `_contracts`, `_ledger`, `_billing`, `_reports`, `_beats`, `_coach`, `_intelligence`, `_export`, `_accounts`, `_devices`, `_signals`, `_suggestions`, `_integrations`), with the HTTP contract that belongs to no one router left in `test_api.py`. The open decision — where the shared fixtures live — is settled: `api/src/api_helpers.py`, beside `conftest.py` and not `test_`-prefixed, so pytest does not collect it and no suite imports another |
| `api/src/beats/test_domain.py` (~5 900) | By the domain module under test: `test_models`, `test_analytics`, `test_intelligence`, `test_planning`, `test_focus`, `test_services`, `test_project_service`, `test_project_aggregations`, `test_health_integrations`, `test_dev_integrations`, over `beats/domain_fakes.py` |
| `api/src/beats/test_coach.py` (~4 280) | By surface: `test_coach` (usage, cost, pricing, cache control), `test_coach_gateway`, `test_coach_briefs`, `test_coach_memory`, `test_coach_chat`, `test_coach_tools`, `test_coach_context`, `test_coach_day_context`, over `beats/coach_fakes.py` |
| `api/src/test_organisations.py` (~3 120) | The stage seam: `test_organisations` (the stage-2 contract, the wall with it), `test_organisations_projects`, `test_organisations_closing`, `test_employment`, over `organisation_helpers.py` |
| `api/src/beats/domain/models.py` (1 968) | `models_contracts.py`, `models_billing.py` and `models_organisations.py`, re-exported from `models.py` with `__all__`. The re-export indirection **was** worth it: every import site names `models`, and the one-way dependency (contracts knows neither of the others; organisations reads contracts) means the facade cannot cycle |
| `api/src/beats/infrastructure/repositories.py` (1 586) | `project_repositories.py`, `contract_repositories.py`, `billing_repositories.py` and `signal_repositories.py`; `repositories.py` keeps `MongoStore`, the serializers and the long tail of one-model repositories. Import sites name the new module directly — no re-export, because unlike `models.py` the names are few per site |
| `api/src/beats/domain/organisations.py` (1 360) | `organisation_record.py` — the record and archive shapes and the two assemblies that fill them, taking the store and the record reader rather than a service, as `ledger.py` and `timesheet.py` do |
| `api/src/beats/test_auth.py` (1 342) | `test_auth.py` (the session manager) and `test_webauthn.py`, over `beats/auth_fakes.py` |
| `api/src/beats/domain/services.py` (1 313) | `contract_service.py`, beside the `contracts.py` arithmetic it reads |
| `api/src/beats/infrastructure/organisations.py` (1 202) | `organisation_records.py` for `MongoOrganisationRecords` |
| `api/src/beats/api/schemas.py` (1 009) | `schemas_billing.py` and `schemas_organisations.py`, re-exported from `schemas.py` the same way `models.py` does it |

## Work

- **`api/src/beats/domain/organisations.py` is 1 087 lines, still 9% over.**
  The closing-and-deletion block and the operator twins (~215 lines together)
  are what would bring it under, and the roadmap's own note said to weigh that:
  each twin was put beside the member's method it twins, and the comment above
  them explains the pair. Moving them means either a mixin whose `self.store`
  and `self._member` the type checker cannot see, or a fourth class in the
  inheritance chain (core → closing → organisations → employment). Neither is
  obviously better than being 87 lines over; decide deliberately rather than
  mechanically.
