#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Build the sample pack. Thin wrapper; the builder lives in evidence.packs.credit_underwriting.

    python scripts/build_sample_pack.py --n 700 --keep 20 --seed 7 [--spec path.yaml]
"""

from evidence.packs.credit_underwriting import main

if __name__ == "__main__":
    main()
