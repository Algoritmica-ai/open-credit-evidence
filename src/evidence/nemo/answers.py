# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Reading a multiple-choice answer the way models actually write it."""

from __future__ import annotations

import re

# "Answer: D", and the forms models copy from a template or a maths habit:
# "Answer: $D$", "Answer: (D)", "Answer: **D**", "Answer: \boxed{D}"
ANSWER = re.compile(r"(?i)Answer\s*:\s*[\s$*(\[{]*(?:\\boxed\{|\\text\{)?\s*([A-J])\b")


def letter(response: str) -> str | None:
    """The letter on the last answer line, or None."""
    found = ANSWER.findall(response)
    return found[-1].upper() if found else None
