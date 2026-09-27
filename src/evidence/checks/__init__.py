# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Deterministic checks — grading that needs no model and no rubric argument.

Every check is domain-agnostic. If a check here needs to know what a "loan"
is, the abstraction has failed. Checks resolve model output against the
reference lists an item carries; they never see the answer key.

A check that changes what it passes gets a new version. A run records the versions it
was scored with, and a check keeps its earlier versions runnable, so a sealed run
re-derives exactly as it was scored and the effect of a new version can be shown on it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from evidence.contracts.check import CheckResult
from evidence.contracts.item import BenchmarkItem

CheckFn = Callable[..., CheckResult]
_REGISTRY: dict[str, CheckFn] = {}
_VERSIONS: dict[str, int] = {}


def check(name: str, version: int = 1) -> Callable[[CheckFn], CheckFn]:
    """Register a check under the name items refer to it by, at its current version.

    A check above version 1 takes ``version=`` and still runs its earlier versions.
    """

    def register(fn: CheckFn) -> CheckFn:
        _REGISTRY[name] = fn
        _VERSIONS[name] = version
        fn.check_name = name  # type: ignore[attr-defined]
        return fn

    return register


def check_versions(names: list[str] | None = None) -> dict[str, int]:
    """The current version of each named check (all of them by default)."""
    return {n: _VERSIONS[n] for n in (names if names is not None else sorted(_VERSIONS))}


def available_checks() -> list[str]:
    return sorted(_REGISTRY)


def run_checks(names: list[str], *, output: str, item: BenchmarkItem,
               versions: dict[str, int] | None = None) -> list[CheckResult]:
    """Run the named checks against one model output, at their current versions unless
    ``versions`` names others (a run scored before a check changed)."""
    results: list[CheckResult] = []
    for name in names:
        try:
            fn = _REGISTRY[name]
        except KeyError as exc:
            raise KeyError(f"unknown check {name!r}; available: {available_checks()}") from exc
        v = (versions or {}).get(name, _VERSIONS[name])
        if not 1 <= v <= _VERSIONS[name]:
            raise ValueError(f"{name} has no version {v}; current is {_VERSIONS[name]}")
        extra = {"version": v} if _VERSIONS[name] > 1 else {}
        results.append(fn(output=output, item=item, **extra))
    return results


def _load_all() -> None:
    # Importing registers. Kept explicit so a missing module is a loud failure.
    from evidence.checks import claims, comparison, decoy, flip, numeric, omission  # noqa: F401


_load_all()

__all__: list[Any] = ["CheckResult", "available_checks", "check", "check_versions",
                      "run_checks"]
