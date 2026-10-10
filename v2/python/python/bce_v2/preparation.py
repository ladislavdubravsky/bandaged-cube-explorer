"""Measured preparation workload and conservative backend routing.

Geometry signatures are deliberately absent: the complete group's order and
actual witnessed-loop workload decide feasibility, rather than block names.
"""

from .computation import current_computation, report_progress
from .isotropy import IsotropyAnalysis, analyze_isotropy, isotropy_loops


def validate_stage_inputs(strategy, features):
    from .human_chains import BlockFeature
    if strategy not in ("fully_solve_each_block", "placement_then_orientation", "manual"):
        raise ValueError("unknown human stage strategy")
    if strategy != "manual":
        if features is not None:
            raise ValueError("features are only accepted with strategy='manual'")
        return None
    if features is None:
        raise ValueError("manual strategy requires features")
    features = tuple(features)
    if any(not isinstance(feature, BlockFeature) for feature in features):
        raise TypeError("manual features must be BlockFeature instances")
    return features


def validate_search_inputs(discovery_options=None, dictionary=None, dictionary_options=None):
    """Reject malformed discovery settings before automatic routing runs GAP."""
    from inspect import signature
    from .gap_backend import _validated_options
    from .symbolic_dictionary import SymbolicAlgorithmDictionary, discover_symbolic_dictionary
    from .human_chain_search import _DISCOVERY_DEFAULTS

    if discovery_options is not None:
        if not isinstance(discovery_options, dict):
            raise TypeError("discovery_options must be a dictionary or None")
        if set(discovery_options) - set(_DISCOVERY_DEFAULTS):
            raise ValueError("unknown discovery option")
        for name, value in discovery_options.items():
            if name == "mode":
                if value not in ("original", "shallow", "structured"):
                    raise ValueError("unknown discovery mode")
            elif type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            elif value < (1 if name == "max_alternatives" else 0):
                raise ValueError(f"invalid discovery budget: {name}")
    if dictionary is not None and not isinstance(dictionary, SymbolicAlgorithmDictionary):
        raise TypeError("dictionary must be a SymbolicAlgorithmDictionary")
    if dictionary is not None and dictionary_options is not None:
        raise ValueError("dictionary_options cannot be supplied with a prepared dictionary")
    if dictionary_options is not None:
        if not isinstance(dictionary_options, dict):
            raise TypeError("dictionary_options must be a dictionary or None")
        if set(dictionary_options) - (set(signature(discover_symbolic_dictionary).parameters) - {"initial"}):
            raise ValueError("unknown dictionary option")
        for name, value in dictionary_options.items():
            if name in ("gap_executable", "timeout"):
                continue
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < (1 if name in ("max_algorithms", "max_htm_length", "max_expanded_moves") else 0):
                raise ValueError(f"invalid dictionary budget: {name}")
        _validated_options(dictionary_options.get("gap_executable", "gap"), dictionary_options.get("timeout"))


def reference_loops(method):
    """Reuse native provenance; portable inputs still get native coverage checks."""
    context = current_computation()
    loops = getattr(context, "loops", None)
    if loops is not None and loops.root_shape == method.reference_shape and loops.root_vertex == method.root_vertex:
        return loops
    if method.generators:
        from .loop_algorithms import _loops_from_records
        candidate = _loops_from_records(method.generators)
        if callable(getattr(candidate._native, "transport", None)):
            loops = candidate
        else:
            loops = getattr(candidate._native, "_complete_loops", None)
            if loops is None:
                loops = isotropy_loops(method.reference_shape)
    else:
        loops = isotropy_loops(method.reference_shape)
    if context is not None:
        context.loops = loops
    return loops


def prepare_analysis(initial, *, gap_executable="gap", timeout=None, root=None):
    if isinstance(initial, IsotropyAnalysis):
        analysis = initial
    else:
        analysis = getattr(initial, "analysis", None)
        if analysis is None:
            report_progress("analysis", "started")
            analysis = analyze_isotropy(initial, gap_executable=gap_executable, timeout=timeout, root=root)
    if root is not None and root != analysis.loops.root_vertex:
        raise ValueError("root differs from the supplied reference analysis")
    report_progress("analysis", "completed", group_order=analysis.group_order,
                    shapes=analysis.loops.shape_count, original_loops=len(analysis.loops.generators),
                    algebra_generators=len(analysis.generators))
    context = current_computation()
    if context is not None:
        context.loops = analysis.loops
    return analysis


def preparation_profile(analysis):
    """Return exact group and cheap witness metadata from an existing analysis."""
    if not isinstance(analysis, IsotropyAnalysis):
        raise TypeError("preparation_profile requires an IsotropyAnalysis")
    loops, basis = analysis.loops, analysis.generators
    originals = loops.generators
    original_work = sum(g.qtm_length for g in originals)
    basis_work = sum(g.qtm_length for g in basis)
    observable = sum(bool(block.corners or block.edges) for block in analysis.block_inventory.blocks)
    # Explicit closure stores every reference-group member and block summary.
    # Large witness libraries also make repeated exact explicit quality trials
    # expensive. Keep the conservative envelope inspectable in the profile.
    explicit_eligible = analysis.group_order <= 20_000
    explicit_work = analysis.group_order * max(1, observable)
    backend = "explicit" if (explicit_eligible and explicit_work <= 250_000
                              and len(originals) <= 256 and basis_work <= 512) else "symbolic"
    large = len(originals) > 128 or original_work > 10_000 or loops.shape_count > 1_000
    return dict(group_order=analysis.group_order, shape_count=loops.shape_count,
                arc_count=loops.arc_count, original_loop_count=len(originals),
                reduced_generator_count=len(basis), original_qtm_sum=original_work,
                original_qtm_max=max((g.qtm_length for g in originals), default=0),
                reduced_qtm_sum=basis_work, reduced_qtm_max=max((g.qtm_length for g in basis), default=0),
                observable_blocks=observable, explicit_group_eligible=explicit_eligible,
                estimated_explicit_block_entries=explicit_work,
                recommended_backend=backend, graph_view="summary" if loops.shape_count > 1_000 else "full",
                discovery_policy="bounded_physical_pool" if large else "full_small_pool")


def route_preparation(initial, *, gap_executable="gap", timeout=None, root=None,
                      max_group_elements=None):
    if max_group_elements is not None:
        if type(max_group_elements) is not int:
            raise TypeError("max_group_elements must be a positive integer or None")
        if max_group_elements <= 0:
            raise ValueError("max_group_elements must be positive")
    if root is not None and type(root) is not int:
        raise TypeError("root must be an integer vertex ID")
    analysis = prepare_analysis(initial, gap_executable=gap_executable, timeout=timeout, root=root)
    profile = preparation_profile(analysis)
    # An explicit enumeration cap expresses an explicit-backend request.
    backend = "explicit" if max_group_elements is not None else profile["recommended_backend"]
    profile["selected_backend"] = backend
    context = current_computation()
    if context is not None:
        context.profile = profile
    report_progress("routing", "completed", **profile)
    return analysis, backend
