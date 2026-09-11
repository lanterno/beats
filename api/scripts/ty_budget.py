"""Fail if `ty check` reports more diagnostics than the recorded budget.

The project cannot set `error-on-warning = true` yet, but what is left is now
friction between ty and the frameworks rather than anything wrong in the code:
pydantic-settings filling required fields from the environment, Starlette's
deliberately wide exception-handler signature, and a union the Anthropic SDK
yields. Until those resolve upstream this keeps the count from drifting upward
— a new diagnostic fails CI even though the existing ones don't.

Lower BUDGET whenever the real number drops. It is a ceiling, not a target.
"""

import re
import subprocess
import sys

BUDGET = 18


def main() -> int:
    result = subprocess.run(
        ["uv", "run", "--group", "dev", "ty", "check", "src/"],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    match = re.search(r"Found (\d+) diagnostics?", output)
    if match is None:
        if "All checks passed" in output or result.returncode == 0:
            count = 0
        else:
            print(output, file=sys.stderr)
            print("ty-budget: could not read a diagnostic count from ty", file=sys.stderr)
            return 2
    else:
        count = int(match.group(1))

    if count > BUDGET:
        print(output, file=sys.stderr)
        print(
            f"ty-budget: {count} diagnostics, budget is {BUDGET}. "
            f"{count - BUDGET} new one(s) — fix them rather than raising the budget.",
            file=sys.stderr,
        )
        return 1

    if count < BUDGET:
        print(f"ty-budget: {count} diagnostics, budget {BUDGET}. Lower BUDGET to {count}.")
    else:
        print(f"ty-budget: {count} diagnostics, at budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
