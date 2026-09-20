# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The evidence pack: what a validator reads, and the verifier that re-checks it."""

from evidence.evidence.verify import verify_run
from evidence.evidence.writer import write_evidence

__all__ = ["verify_run", "write_evidence"]
