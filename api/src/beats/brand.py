"""The product's name, as people see it.

The API mostly speaks to programs, but a few of its strings reach a person:
the WebAuthn relying-party name the browser prints in the passkey prompt, and
error messages the SPA shows as they are. Those read this constant.

Stamped from `shared/brand.json` by `scripts/gen_brand.py`, which also writes it
into the SPA and the companion — edit the JSON and rerun the script, not this
line.
"""

APP_NAME = "LifePete"
