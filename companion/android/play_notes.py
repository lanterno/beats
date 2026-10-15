"""A GitHub release's notes, as Google Play's "What's new" for the release.

Play shows plain text, at most 500 characters per language. GitHub's notes are
Markdown, and the generated ones end every line with " by @someone in <PR url>"
and finish on a "Full Changelog" link — noise on a phone. This keeps the words:

    NOTES="$(gh release view companion-v1.2.0 --json body -q .body)" \\
        python3 play_notes.py

Reads $NOTES, prints the text. Empty notes print nothing, and Play then shows
none. `python3 -m doctest play_notes.py` runs the examples below.
"""

import os
import re

LIMIT = 500


def play_notes(markdown: str, limit: int = LIMIT) -> str:
    """Markdown release notes → plain text that fits Play's limit.

    >>> play_notes('''## What's Changed
    ... * Pairing opens without the keyboard by @lanterno in https://github.com/lanterno/beats/pull/202
    ... * **Focus** has a Stop button on phones by @lanterno in https://github.com/lanterno/beats/pull/201
    ...
    ... **Full Changelog**: https://github.com/lanterno/beats/compare/companion-v1.0.0...companion-v1.1.0''')
    '• Pairing opens without the keyboard\\n• Focus has a Stop button on phones'

    >>> play_notes('### Fixes\\n- See [the docs](https://example.com) and `flags`\\n\\n\\n- Faster sync')
    'Fixes\\n• See the docs and flags\\n\\n• Faster sync'

    Whole lines are dropped to fit, with a last line saying there is more:

    >>> notes = play_notes('\\n'.join(f'- Change number {i}' for i in range(60)))
    >>> len(notes) <= LIMIT, notes.splitlines()[-1]
    (True, '…and more')

    A single line longer than the limit is cut at a word:

    >>> one = play_notes('word ' * 200)
    >>> len(one) <= LIMIT and one.endswith('…')
    True
    >>> play_notes('   ')
    ''

    Underscores inside a word are not emphasis:

    >>> play_notes('- `--dart-define-from-file` reads use_lifepete_json and __init__')
    '• --dart-define-from-file reads use_lifepete_json and init'
    """
    lines: list[str] = []
    for raw in markdown.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if re.match(r"^\**Full Changelog\**:", line) or line.lower().strip("# ") == "what's changed":
            continue
        line = re.sub(r" by @[\w-]+ in https://\S+$", "", line)  # generated-notes suffix
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)  # [text](url) → text
        line = re.sub(r"^#{1,6}\s*", "", line)  # headings
        line = re.sub(r"^[*-]\s+", "• ", line)  # bullets
        line = re.sub(r"(?<!\w)([*_`]{1,3})([^*_`\n]+?)\1(?!\w)", r"\2", line)  # emphasis, code
        if line or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()

    text = "\n".join(lines)
    if len(text) <= limit:
        return text

    more = "…and more"
    kept: list[str] = []
    for line in lines:
        if len("\n".join([*kept, line, more])) > limit:
            break
        kept.append(line)
    if kept:
        return "\n".join([*kept, more])
    # One line on its own is too long: cut it at a word.
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip()
    return cut + "…"


if __name__ == "__main__":
    print(play_notes(os.environ.get("NOTES", "")), end="")
