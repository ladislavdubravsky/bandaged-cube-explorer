"""Compilation-local progress and shared optional quality-search budgets.

Certification precedes the budget. A cutoff can return a previously certified
artifact, never turn an interrupted proof into a completeness claim. The final
portable fallback and its mandatory validation run outside quality search.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
import json
from math import isfinite
from time import monotonic


_CURRENT = ContextVar("bce_computation", default=None)


class OptimizationBudgetExceeded(RuntimeError):
    """An optional pass exhausted the compilation's shared quality allowance."""


def current_computation():
    return _CURRENT.get()


class Computation:
    def __init__(self, *, optimization_seconds=None, max_optimization_work=None, progress=None):
        if optimization_seconds is not None:
            if isinstance(optimization_seconds, bool) or not isinstance(optimization_seconds, (int, float)):
                raise TypeError("optimization_seconds must be a nonnegative finite number or None")
            if not isfinite(optimization_seconds) or optimization_seconds < 0:
                raise ValueError("optimization_seconds must be nonnegative and finite")
        if max_optimization_work is not None:
            if type(max_optimization_work) is not int:
                raise TypeError("max_optimization_work must be a nonnegative integer or None")
            if max_optimization_work < 0:
                raise ValueError("max_optimization_work must be nonnegative")
        if progress is not None and not callable(progress):
            raise TypeError("progress must be callable or None")
        self.seconds = optimization_seconds
        self.limit = max_optimization_work
        self.progress = progress
        self.started = monotonic()
        self.quality_started = None
        self.work = 0
        self.stop_reason = None
        self.best_method = None
        self.best_repertoire = None
        self.best_method_rank = None
        self.best_repertoire_rank = None
        self.profile = None
        self.method_preference = "execution"
        self._suspended = 0
        self._last_phase = None
        self._last_event = float("-inf")

    @contextmanager
    def activate(self):
        token = _CURRENT.set(self)
        try:
            yield self
        finally:
            _CURRENT.reset(token)

    @contextmanager
    def suspend(self):
        self._suspended += 1
        try:
            yield
        finally:
            self._suspended -= 1

    def event(self, phase, status="running", **details):
        now = monotonic()
        if status == "running" and phase == self._last_phase and now - self._last_event < .5:
            return
        self._last_phase, self._last_event = phase, now
        if self.progress is not None:
            self.progress(dict(phase=phase, status=status, elapsed_seconds=round(now - self.started, 3),
                               optimization_work=self.work, **details))

    def check(self, phase, work=1, **details):
        if type(work) is not int or work < 0:
            raise ValueError("checkpoint work must be a nonnegative integer")
        if self.quality_started is not None and not self._suspended:
            reason = None
            if self.seconds is not None and monotonic() - self.quality_started >= self.seconds:
                reason = "optimization_seconds"
            elif self.limit is not None and self.work + work > self.limit:
                reason = "max_optimization_work"
            if reason is not None:
                self.stop_reason = reason
                self.event(phase, "budget_exhausted", reason=reason)
                raise OptimizationBudgetExceeded(reason)
            self.work += work
        self.event(phase, **details)

    def retain_method(self, method, source="certified_baseline", metrics=None):
        if method.status != "completed":
            return
        if self.quality_started is None:
            self.best_method = method
            self.quality_started = monotonic()
            self.event("baseline", "certified", source=source, group_order=method.group_order,
                       stages=len(method.stages), cases=sum(s.case_count for s in method.stages))
        # Compare one scope, including explicit optimizers whose other metrics
        # may include boundary cancellation.
        costs = method.additive_costs()["htm"]
        rank = (costs["mean"], costs["worst"], len(method.stages))
        if self.method_preference == "recognition":
            rank = (max((stage.case_count for stage in method.stages), default=0),
                    sum(stage.case_count for stage in method.stages), *rank)
        if self.best_method_rank is None or rank < self.best_method_rank:
            self.best_method, self.best_method_rank = method, rank
            self.event("method", "retained", source=source, mean_htm=costs["mean"], worst_htm=costs["worst"])

    def retain_repertoire(self, repertoire):
        metadata = repertoire.metadata
        preference = metadata["settings"]["preference"]
        order = metadata["preference_orders"][preference]
        metrics = metadata["selected_metrics"]
        rank = tuple(metrics[key] for key in order)
        if self.best_repertoire_rank is None or rank < self.best_repertoire_rank:
            self.best_repertoire, self.best_repertoire_rank = repertoire, rank
            self.event("repertoire", "retained", macros=len(repertoire.macros),
                       mean_htm=metrics["mean_htm"], worst_htm=metrics["worst_htm"])

    def summary(self):
        return dict(optimization_seconds=self.seconds, max_optimization_work=self.limit,
                    optimization_work=self.work, stop_reason=self.stop_reason,
                    elapsed_seconds=round(monotonic() - self.started, 6),
                    budget_scope="shared optional quality passes after certified baseline; final validation excluded",
                    workload=self.profile)

    @property
    def diagnostics_enabled(self):
        return (self.seconds is not None or self.limit is not None or
                self.progress is not None or self.profile is not None)

    def finish(self, repertoire):
        self.event("complete", "certified", stopped=self.stop_reason is not None,
                   macros=len(repertoire.macros))
        if not self.diagnostics_enabled:
            return repertoire
        metadata = repertoire.metadata
        metadata["computation"] = self.summary()
        return replace(repertoire, _metadata_json=json.dumps(metadata, sort_keys=True, allow_nan=False))


def report_progress(phase, status="running", **details):
    context = current_computation()
    if context is not None:
        context.event(phase, status, **details)


def checkpoint(phase, work=1, **details):
    context = current_computation()
    if context is not None:
        context.check(phase, work, **details)


def retain_method(method, source="certified_baseline", metrics=None):
    context = current_computation()
    if context is not None:
        context.retain_method(method, source, metrics)


def retain_repertoire(repertoire):
    context = current_computation()
    if context is not None:
        context.retain_repertoire(repertoire)


def quality_timeout(timeout):
    context = current_computation()
    if context is None or context.quality_started is None or context._suspended or context.seconds is None:
        return timeout
    context.check("algebra", work=0)
    remaining = max(.000001, context.seconds - (monotonic() - context.quality_started))
    return remaining if timeout is None else min(timeout, remaining)


def validate_computation_metadata(metadata):
    """Check optional execution diagnostics without treating them as a proof."""
    if "computation" not in metadata:
        return
    record = metadata["computation"]
    fields = {"optimization_seconds", "max_optimization_work", "optimization_work", "stop_reason",
              "elapsed_seconds", "budget_scope", "workload"}
    if not isinstance(record, dict) or set(record) != fields:
        raise ValueError("invalid computation diagnostics")
    Computation(optimization_seconds=record["optimization_seconds"],
                max_optimization_work=record["max_optimization_work"])
    if (type(record["optimization_work"]) is not int or record["optimization_work"] < 0
            or record["stop_reason"] not in (None, "optimization_seconds", "max_optimization_work")
            or type(record["elapsed_seconds"]) not in (int, float)
            or not isfinite(record["elapsed_seconds"]) or record["elapsed_seconds"] < 0
            or record["budget_scope"] != "shared optional quality passes after certified baseline; final validation excluded"
            or (record["workload"] is not None and not isinstance(record["workload"], dict))
            or (record["max_optimization_work"] is not None and
                record["optimization_work"] > record["max_optimization_work"])):
        raise ValueError("invalid computation diagnostics")
