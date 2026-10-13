"""One-call palette methods with checked automatic shape restoration.

Inputs describe a bandage, not a preferred ordinary-cube method. The bounded
catalog chooses physically available actions. Small reference groups can use
a completely covered joint-pose policy if a cheaper staged policy is absent;
larger groups require successful preservation-led discovery and bounded entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from time import perf_counter

from . import State, explore, shape
from ._moves import _simplified_moves
from .algorithm_palette import AlgorithmPalette, AlgorithmPaletteBody
from .automatic_palette import automatic_algorithm_palette
from .coarse_methods import CoarseMethod, compile_coarse_method
from .coarse_search import discover_coarse_method
from .computation import Computation, current_computation, report_progress
from .gap_backend import GapTimeoutError, _validated_options
from .human_chains import BlockFeature
from .isotropy import isotropy_loops
from .loop_algorithms import AlgorithmLibrary, LoopExpression
from .notebook_methods import cached_coarse_method
from .palette_policies import recipe_taught_ids
from .workspace_methods import WorkspaceMethod, compile_workspace_method


_JOINT_POLICY_LIMIT = 512
_MAX_ORIGINAL_LOOPS = 256
_MAX_ORIGINAL_WITNESS_QTM = 100_000


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _taught_ids(palette):
    values = recipe_taught_ids(palette, 4)
    return {identifier for row in values.values() for identifier in row}


def _entry_palette(analysis):
    """Use short root operations and the reduced witnessed algebra basis.

    A long loop and its inverse share one explicitly declared body. Squares
    of long loops remain repeated calls instead of extra learned definitions.
    Short adjustments are available independently of suffix preservation.
    """
    library = AlgorithmLibrary(analysis.loops, (), (), ())
    bodies, adjustments, seen = [], [], set()
    for generator in analysis.loops.generators:
        if generator.htm_length > 4:
            continue
        for exponent in (1, 2, -1):
            algorithm = replace(library.build_algorithm(LoopExpression.power(
                LoopExpression.loop(generator.id), exponent)),
                id=f"root:{generator.id}:{exponent}")
            if algorithm.permutation != tuple(range(48)) and algorithm.permutation not in seen:
                if algorithm.htm_length <= 4:
                    adjustments.append(algorithm)
                    seen.add(algorithm.permutation)
    for generator in sorted(analysis.generators, key=lambda value: (value.htm_length, value.id)):
        if generator.htm_length <= 4:
            continue
        algorithm = replace(library.build_algorithm(LoopExpression.loop(generator.id)),
                            id=f"loop:{generator.id}")
        bodies.append(AlgorithmPaletteBody(algorithm.id, algorithm, True))
    short = AlgorithmPalette.from_algorithms((), adjustments=adjustments)
    return AlgorithmPalette(tuple(bodies), adjustments=short.adjustments)


def _workspace_entry_palette(suffix, candidates, budget):
    """Fit declared entry definitions alongside the selected suffix bodies."""
    used = set(suffix.taught_body_ids)
    declarations = {body.id: body for body in suffix.palette.bodies}
    bodies, reserved = [], set(used)
    for candidate in candidates.bodies:
        prior = declarations.get(candidate.id)
        if prior is not None:
            # Preserve exact permissions when sharing a teaching ID.
            if (prior.algorithm.turn_sequence != candidate.algorithm.turn_sequence or
                    prior.algorithm.permutation != candidate.algorithm.permutation):
                raise ValueError("automatic entry and continuation disagree on a shared body")
            candidate = prior
        if candidate.id not in reserved and len(reserved) >= budget:
            continue
        reserved.add(candidate.id)
        bodies.append(candidate)
    return AlgorithmPalette(tuple(bodies), adjustments=candidates.adjustments)


@dataclass(frozen=True)
class AutomaticMethodApplication:
    status: str
    state: State
    shape_turn_sequence: str = ""
    method_application: object | None = None
    reason: str | None = None

    @property
    def turn_sequence(self):
        continuation = (self.method_application.turn_sequence
                        if self.method_application is not None else "")
        return _simplified_moves((self.shape_turn_sequence + " " + continuation).split())

    @property
    def htm_length(self):
        return len(self.turn_sequence.split())


@dataclass(frozen=True)
class AutomaticMethod:
    inner_method: CoarseMethod | WorkspaceMethod
    graph: object = field(repr=False)
    _metadata_json: str = field(repr=False)

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    @property
    def reference_shape(self):
        return self.inner_method.reference_shape

    @property
    def coverage_complete(self):
        return (self.graph.complete and isinstance(self.inner_method, CoarseMethod) and
                self.inner_method.group_order == self.inner_method.ambient_group_order)

    @property
    def coverage_scope(self):
        return ("complete_reachable_shape_component" if self.coverage_complete else
                "shape_restoration_then_bounded_entry_and_certified_domain_suffix")

    @property
    def human_method_complete(self):
        # Graph restoration is a complete computational policy. Its human
        # recognition and instruction compression have not been established.
        return self.coverage_complete and len(self.graph) == 1

    def apply(self, state):
        if not isinstance(state, State):
            raise TypeError("automatic method requires a colored State")
        if state.specification != self.reference_shape:
            return AutomaticMethodApplication("wrong_reference", state,
                reason="state has another reference specification")
        try:
            vertex = self.graph.vertex_id(state.shape)
        except ValueError:
            return AutomaticMethodApplication("outside_shape_component", state,
                reason="state shape is outside the retained complete component")
        transport = self.graph.shortest_path(vertex, self.reference_shape)
        restored = state.apply(transport)
        if restored.shape != self.reference_shape:
            raise AssertionError("automatic shape restoration failed its exact endpoint")
        application = self.inner_method.apply(restored)
        result = AutomaticMethodApplication(application.status, application.state,
                    transport, application, application.reason)
        if state.apply(result.turn_sequence) != result.state:
            raise AssertionError("automatic complete word disagrees with independent native replay")
        return result

    def write_guide(self, path=None, *, recognition_diagrams=False, face_colors=None):
        lines = ["# Solution", "",
            f"Route: `{self.metadata['route']}`. Coverage: `{self.coverage_scope}`.", "",
            f"The bandage shape graph contains {len(self.graph):,} shapes.", "",
            "The solution below assumes you're in the solved (reference) bandage shape already. "
            "To get there, you need to find a path yourself or ask the tooling to give you "
            "the shortest one for a particular scramble, or read it out of the bandage "
            "shapes graph if small enough (see `shapes-graph-navigation`). "
            "An extractable general strategy is a future goal.", "",
            self.inner_method.write_guide(recognition_diagrams=recognition_diagrams,
                                          face_colors=face_colors)]
        result = "\n".join(lines)
        if path is not None:
            Path(path).write_text(result, encoding="utf-8")
        return result


@dataclass(frozen=True)
class MethodDiscoveryResult:
    status: str
    method: AutomaticMethod | None
    _metadata_json: str = field(repr=False)

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    def apply(self, state):
        if self.method is None:
            raise RuntimeError("discovery has no executable method: " + self.status)
        return self.method.apply(state)

    def write_guide(self, path=None, *, recognition_diagrams=False, face_colors=None):
        if self.method is None:
            raise RuntimeError("discovery has no guide: " + self.status)
        return self.method.write_guide(path, recognition_diagrams=recognition_diagrams,
                                       face_colors=face_colors)


def _cache_directory(value):
    if value is None:
        return None
    if value == "auto":
        for directory in (Path.cwd(), *Path.cwd().parents):
            if (directory / "v2/python/python/bce_v2").is_dir():
                return directory / "v2/.cache/human-methods"
        return Path.cwd() / ".bce-cache/human-methods"
    return Path(value)


def discover_method(initial, *, max_taught_bodies=7, max_shapes=10_000,
                    cache_dir="auto", force=False, progress=None, timeout=90):
    """Select and compile a witnessed method from a bandage alone.

    No algorithms, workspace, recognition goals or planner tuning are required.
    Defaults bound shape exploration and method search. Failure to find a
    method within these limits is reported, not treated as impossibility.

    Shared algorithm preservation drives the larger-group route. Its entry
    remains bounded. Groups of at most 512 elements can instead receive a
    completely certified joint-pose repair policy in the same strict palette
    machinery, with its potentially larger recognition table reported.
    Shape restoration is automatic for both routes and ignores move history.
    ``timeout`` bounds each GAP operation, not total discovery wall time.
    Set ``cache_dir=None`` to disable the revalidated continuation cache.
    """
    for name, value, minimum in (("max_taught_bodies", max_taught_bodies, 0),
                                ("max_shapes", max_shapes, 1)):
        if type(value) is not int:
            raise TypeError(name + " must be an integer")
        if value < minimum:
            raise ValueError(name + " is below its minimum")
    if type(force) is not bool:
        raise TypeError("force must be a boolean")
    if progress is not None and not callable(progress):
        raise TypeError("progress must be callable or None")
    _validated_options("gap", timeout)
    directory = _cache_directory(cache_dir)
    reference = initial.specification if isinstance(initial, State) else shape(initial)
    if progress is not None and current_computation() is None:
        with Computation(progress=progress).activate():
            return discover_method(reference, max_taught_bodies=max_taught_bodies,
                max_shapes=max_shapes, cache_dir=directory, force=force, timeout=timeout)
    started = perf_counter()
    metadata = {"algorithms_supplied_by_caller": False, "goals_supplied_by_caller": False,
                "max_taught_bodies": max_taught_bodies, "max_shapes": max_shapes,
                "bounded_search": True, "joint_policy_group_limit": _JOINT_POLICY_LIMIT,
                "unrestricted_colored_solver_used": False, "attempts": []}

    def result(status, inner=None, graph=None):
        metadata["status"] = status
        metadata["wall_seconds"] = perf_counter() - started
        method = None
        if inner is not None:
            method = AutomaticMethod(inner, graph, _json(metadata))
            metadata["coverage_scope"] = method.coverage_scope
            metadata["coverage_complete"] = method.coverage_complete
            metadata["human_method_complete"] = method.human_method_complete
            method = replace(method, _metadata_json=_json(metadata))
        return MethodDiscoveryResult(status, method, _json(metadata))

    report_progress("automatic_shape_graph", "started", max_shapes=max_shapes)
    graph = explore(reference, max_vertices=max_shapes)
    metadata.update(shape_count=len(graph), shape_graph_complete=graph.complete)
    if not graph.complete:
        metadata["reason"] = "shape exploration reached max_shapes before completing the component"
        return result("analysis_limit")
    try:
        loops = isotropy_loops(graph)
        witness_work = sum(generator.qtm_length for generator in loops.generators)
        metadata.update(original_loop_count=len(loops.generators),
                        original_witness_qtm=witness_work)
        if len(loops.generators) > _MAX_ORIGINAL_LOOPS or witness_work > _MAX_ORIGINAL_WITNESS_QTM:
            metadata["reason"] = "original-loop workload exceeds the automatic preparation envelope"
            return result("preparation_limit")
        analysis = loops.analyze(timeout=timeout)
        metadata["reference_group_order"] = str(analysis.group_order)
        automatic = automatic_algorithm_palette(analysis, max_taught_bodies=max_taught_bodies)
        metadata["automatic_palette"] = automatic.metadata
        # Preserve the small, measured ordinary search envelope. The same
        # limits apply to every geometry, without a cube-identity dispatch.
        options = dict(max_taught_bodies=max_taught_bodies, beam_width=1,
                       max_expansions=6, max_stages=6, max_candidates=8,
                       max_observations=128, preference="recognition", timeout=timeout)
        if directory is None:
            search = discover_coarse_method(analysis, palette=automatic.palette, **options)
            suffix, search_record = search.method, search.to_dict(include_method=False)
            metadata["cache"] = {"cache_status": "disabled", "cache_hit": False}
        else:
            cached = cached_coarse_method(analysis, automatic.palette, directory,
                                         force=force, **options)
            suffix, search_record = cached.method, cached.search_record
            metadata["cache"] = cached.metadata
        metadata["coarse_search"] = search_record
        entry = _entry_palette(analysis)
        if suffix is not None and suffix.group_order == analysis.group_order:
            metadata.update(route="palette_staged_policy",
                            taught_definition_ids=list(suffix.taught_body_ids),
                            stage_case_counts=[stage.case_count for stage in suffix.stages])
            return result("completed", suffix, graph)
        if suffix is not None and (suffix.group_order > 1 or analysis.group_order > _JOINT_POLICY_LIMIT):
            palette = _workspace_entry_palette(suffix, entry, max_taught_bodies)
            combined = set(suffix.taught_body_ids) | _taught_ids(palette)
            required = {body.id for body in entry.bodies}
            admitted = {body.id for body in palette.bodies}
            if len(combined) <= max_taught_bodies and required <= admitted:
                longest = max((recipe.htm_length for recipe in palette.recipes), default=1)
                inner = compile_workspace_method(suffix, entry_palette=palette,
                    max_taught_bodies=max_taught_bodies, max_candidates=6, max_entry_nodes=100_000,
                    controller_options={"max_depth": max(12, 4 * longest), "max_nodes": 20_000})
                metadata.update(route="palette_workspace",
                                taught_definition_ids=list(inner.taught_definition_ids),
                                entry_alphabet_generates_reference_group=True,
                                stage_case_counts=[stage.case_count for stage in suffix.stages])
                return result("completed", inner, graph)
            metadata["attempts"].append(
                "complete generating entry alphabet cannot fit alongside the suffix within the teaching budget")
        if analysis.group_order <= _JOINT_POLICY_LIMIT and len(_taught_ids(entry)) <= max_taught_bodies:
            # Full pose of every physical component is a faithful observation.
            # The small exact orbit is bounded before constructing its cases.
            cells = tuple(cell for block in analysis.block_inventory.blocks for cell in block.cells)
            features = (BlockFeature("solve_blocks", cells),) if analysis.group_order > 1 else ()
            joint = compile_coarse_method(analysis, features=features, palette=entry, timeout=timeout)
            if joint.group_order != analysis.group_order:
                raise AssertionError("automatic joint policy has an entry assumption")
            metadata.update(route="palette_joint_policy", goals_derived_from="faithful_component_poses",
                            taught_definition_ids=list(joint.taught_body_ids),
                            stage_case_counts=[stage.case_count for stage in joint.stages],
                            recognition_scope="bounded complete joint-pose table; no human quality claim")
            return result("completed", joint, graph)
        metadata["reason"] = "no executable method found within the automatic vocabulary and search limits"
        return result("no_method_found")
    except GapTimeoutError as error:
        metadata["reason"] = str(error)
        return result("computation_timeout")


__all__ = ["AutomaticMethod", "AutomaticMethodApplication", "MethodDiscoveryResult", "discover_method"]
