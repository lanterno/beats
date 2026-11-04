"""The operator's side of the API (docs/backoffice.md).

A package for a surface, beside the domain it uses, the way `beats/coach/`
is. Composed only by `operator_server.py` — the public API never imports it,
and nothing here may import `beats.settings`, `beats.auth` or
`beats.api.dependencies`, each of which loads the API's secrets.
"""
