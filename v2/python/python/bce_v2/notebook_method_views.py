"""Compact notebook views of certified continuations and bounded entry.

These views read the compiled method and actual application records. They do
not infer sample coverage or substitute stored research measurements for live
execution. Every component label comes from the method's physical inventory.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from math import isfinite

from ._moves import _simplified_moves
from .coarse_methods import CoarseMethod, _palette_record
from .human_chains import _feature_indices
from .human_methods import HumanMethodApplication
from .human_render import _feature_name
from .workspace_methods import WorkspaceMethod, WorkspaceMethodApplication


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def _word(value):
    return "`" + _cell(value or "(no moves)") + "`"


def _table(headings, rows):
    return "\n".join([
        "| " + " | ".join(headings) + " |",
        "| " + " | ".join("---" for _ in headings) + " |",
        *("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows),
    ])


def _indices(inventory, features):
    return {index for feature in features for index in _feature_indices(inventory, feature)}


def _calls(palette, identifiers):
    from .palette_render import expanded_recipe_path

    records = {record["id"]: record for record in palette.recipe_records}
    calls = []
    for identifier in expanded_recipe_path(palette, identifiers):
        record = records[identifier]
        name = record["body_id"] or record["adjustment_id"]
        if record["exponent"] < 0:
            name += "⁻¹"
        setup = record["setup_id"]
        calls.append(_word(f"[{setup}: {name}]" if setup is not None else name))
    return " → ".join(calls) or "—"


def _palette_signature(record):
    """Bind physical words and effects without requiring identical proof trees."""
    return tuple((kind, tuple(sorted((entry["id"],
                    entry["allow_inverse"] if kind == "bodies" else None,
                    entry["algorithm"]["turn_sequence"],
                    tuple(entry["algorithm"]["permutation"])) for entry in record[kind])))
                 for kind in ("bodies", "setups", "adjustments"))


def coarse_method_overview(method):
    """Markdown goals, vocabulary and exact additive uniform-domain costs."""
    if not isinstance(method, CoarseMethod):
        raise TypeError("method must be a CoarseMethod")
    algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
    recipe_paths = {(number, observation): path
                    for number, observation, path in method.case_recipes}
    stage_rows = []
    for stage in method.stages:
        costs = [0 if case.algorithm_id is None else algorithms[case.algorithm_id].htm_length
                 for case in stage.cases]
        bodies = sorted({body for case in stage.cases
                         for identifier in recipe_paths[stage.number, case.observation]
                         for body in method.palette.recipe_body_ids[identifier]})
        stage_rows.append((stage.number, _feature_name(stage.feature, method.inventory),
                           stage.case_count, f"{float(Fraction(sum(costs), len(costs))):.2f}",
                           max(costs), ", ".join(bodies) or "—"))
    costs = method.additive_costs()["htm"]
    contract = "; ".join(_feature_name(feature, method.inventory)
                         for feature in method.domain_features)
    lines = [
        "### Certified continuation", "",
        "Starting contract: " + (contract or "any state in the reference group") + ".", "",
        f"Coverage: all **{method.group_order:,}** reference-group states satisfying that contract. "
        f"Taught bodies: **{len(method.taught_body_ids)}**. "
        "Case counts include the already-satisfied case.", "",
        f"Exact uniform-domain additive mean: **{costs['mean']:.2f} HTM** "
        "before cancellation between stage words. This is a continuation cost; "
        "entry and concatenated physical execution have separate measurements.", "",
        _table(("Stage", "Goal", "Cases", "Mean stage HTM", "Max stage HTM", "Bodies"), stage_rows),
    ]
    body_rows = [(body.id, _word(body.algorithm.turn_sequence),
                  "Yes" if body.allow_inverse else "No")
                 for body in method.palette.bodies if body.id in method.taught_body_ids]
    if body_rows:
        lines.extend(["", "Body definitions:", "",
                      _table(("Body", "Moves", "Inverse permitted"), body_rows)])
    if method.palette.setups or method.palette.adjustments:
        lines.extend(["", "Declared setups: " +
                      (", ".join(_word(item.id) for item in method.palette.setups) or "none") +
                      ". Standalone adjustments: " +
                      (", ".join(_word(item.id) for item in method.palette.adjustments) or "none") + "."])
    return "\n".join(lines)


def workspace_method_overview(method):
    """Markdown adaptive-entry contract and its certified continuation."""
    if not isinstance(method, WorkspaceMethod):
        raise TypeError("method must be a WorkspaceMethod")
    settings = method.settings
    lines = ["### Adaptive workspace entry", "",
             "Start with the reference bandage shape restored. The controller chooses "
             "collections from the current arrangement and searches for corrections that "
             "restore all previous commitments at their endpoints.", "",
             "Entry is bounded search. Successful sample replays do not certify all "
             "scrambles or a complete finite human recognition policy.", "",
             f"Global taught definitions: **{len(method.taught_definition_ids)} / "
             f"{settings['max_taught_bodies']}**; " +
             (", ".join(_word(identifier) for identifier in method.taught_definition_ids) or "none") + ". "
             f"Entry bounds: {settings['max_entry_nodes']:,} expanded nodes in total, "
             f"{settings['max_stages']} corrections, "
             f"{settings['controller_options']['max_depth']} additive recipe HTM per correction.", ""]
    if method.anchors:
        lines.extend(["Inferred anchor options: " + "; ".join(
            _feature_name(feature, method.inventory) for feature in method.anchors) + ".", ""])
    lines.append(coarse_method_overview(method.suffix))
    return "\n".join(lines)


def coarse_validation_summary(method, record):
    """Render a previous exhaustive replay only when its physical policy matches.

    A report must retain ``validation_palette`` (the serialized body, setup and
    adjustment witnesses) and ``reference_shape`` as well as every case recipe.
    Reports without these bindings remain historical evidence and are not
    attributed to the current notebook method. No artifact paths are opened.
    """
    if not isinstance(method, CoarseMethod):
        raise TypeError("method must be a CoarseMethod")
    absent = ("No matching previous exhaustive native replay is attached to this policy. "
              "The current continuation has certified domain coverage and exact additive "
              "stage costs; its concatenated physical mean is not measured here.")
    if not isinstance(record, dict):
        return absent
    try:
        if (record.get("format") != "bce-v2-discovered-last-layer-acceptance" or
                type(record.get("version")) is not int or record["version"] != 1 or
                record.get("reference_shape") != method.reference_shape.labels or
                _palette_signature(record["validation_palette"]) !=
                    _palette_signature(_palette_record(method.palette)) or
                record.get("coverage_scope") != method.coverage_scope or
                record.get("start_domain_order") != method.group_order or
                str(record.get("ambient_group_order")) != str(method.ambient_group_order) or
                record.get("inferred_workspace_features") !=
                    [feature.to_dict() for feature in method.domain_features] or
                record.get("discovered_stage_features") !=
                    [stage.feature.to_dict() for stage in method.stages] or
                record.get("case_counts") != [stage.case_count for stage in method.stages] or
                record.get("certified_additive_costs") != method.additive_costs() or
                record.get("supplied_long_bodies") !=
                    {body.id: body.algorithm.turn_sequence for body in method.palette.bodies} or
                record.get("used_long_body_ids") != list(method.taught_body_ids) or
                record.get("complete_physical_state_replays") != method.group_order or
                record.get("distinct_native_states") != method.group_order or
                record.get("all_complete_states_solved") is not True or
                record.get("all_cumulative_endpoint_goals_preserved") is not True or
                record.get("loaded_method_replayed_without_gap") is not True or
                record.get("strict_palette_coverage") is not True or
                record.get("unconstrained_fallback_used") is not False):
            return absent
        stage_reports = record["stage_reports"]
        if len(stage_reports) != len(method.stages):
            return absent
        observed_recipes = []
        for stage, report in zip(method.stages, stage_reports):
            if (report["stage"] != stage.number or
                    report["feature"] != stage.feature.to_dict() or
                    report["case_count"] != stage.case_count or
                    str(report["order_before"]) != str(stage.order_before) or
                    str(report["order_after"]) != str(stage.order_after) or
                    report["complete_native_hidden_state_visits"] != method.group_order):
                return absent
            observed_recipes.extend((stage.number, tuple(case["observation"]), tuple(case["recipe"]))
                                    for case in report["cases"])
        if (len(observed_recipes) != len(method.case_recipes) or
                set(observed_recipes) != set(method.case_recipes)):
            return absent
        physical_mean = record["mean_last_layer_physical_htm"]
        physical_worst = record["worst_last_layer_physical_htm"]
        endpoint_checks = record["cumulative_stabilizer_endpoint_checks"]
        if (type(physical_mean) not in (int, float) or not isfinite(physical_mean) or
                physical_mean < 0 or type(physical_worst) is not int or
                physical_worst < physical_mean or type(endpoint_checks) is not int or
                endpoint_checks < 0):
            return absent
    except (KeyError, TypeError, ValueError):
        return absent
    return (f"Previous exhaustive native replay matching this policy: "
            f"**{method.group_order:,} / {method.group_order:,}** distinct starting-domain "
            f"states solved, with **{endpoint_checks:,}** cumulative endpoint checks. "
            f"Mean concatenated physical continuation: **{physical_mean:.2f} HTM**; "
            f"worst: **{physical_worst} HTM**. This retained measurement excludes entry "
            "and is separate from the exact additive stage-word mean above.")


def _application_parts(method, application):
    if isinstance(method, WorkspaceMethod) and isinstance(application, WorkspaceMethodApplication):
        entry = tuple(application.entry_steps)
        suffix = tuple(application.suffix_application.steps) if application.suffix_application else ()
        return method.suffix, entry, suffix
    if isinstance(method, CoarseMethod) and isinstance(application, HumanMethodApplication):
        return method, (), tuple(application.steps)
    raise TypeError("application must match a CoarseMethod or WorkspaceMethod")


def method_application_trace(method, application):
    """Markdown actual correction words, declared calls and prior constraints."""
    suffix, entry_steps, suffix_steps = _application_parts(method, application)
    rows = []
    for number, step in enumerate(entry_steps, 1):
        protected = len(_indices(method.inventory, step.protected_features))
        rows.append((f"Entry {number}", _feature_name(step.feature, method.inventory),
                     _calls(method.entry_palette, step.action_ids), _word(step.turn_sequence),
                     step.htm_length, protected))
    paths = {(number, observation): path for number, observation, path in suffix.case_recipes}
    for step in suffix_steps:
        prior_features = list(suffix.domain_features)
        for stage in suffix.stages[:step.stage_number - 1]:
            prior_features.extend((stage.feature, *stage.implied_features))
        rows.append((f"Continuation {step.stage_number}", _feature_name(step.feature, suffix.inventory),
                     _calls(suffix.palette, paths[step.stage_number, step.observation]),
                     _word(step.turn_sequence), step.htm_length,
                     len(_indices(suffix.inventory, prior_features))))
    lines = [f"Status: **{application.status}**. "
             f"Concatenated execution: **{len(application.turn_sequence.split())} HTM**."]
    if application.reason:
        lines.append("Reason: " + application.reason)
    lines.extend(["", "Only executed corrections appear. Prior constrained components "
                  "count physical components named by earlier goals; orientation and "
                  "relative-placement goals do not imply that those components are fully solved. "
                  "`[setup: body]` means setup, body, undo setup.", ""])
    if rows:
        lines.append(_table(("Correction", "Goal", "Palette calls", "Moves", "HTM",
                             "Prior constrained components"), rows))
    else:
        lines.append("No corrections were executed.")
    return "\n".join(lines)


def workspace_sample_summary(method, applications, *, scrambles=None):
    """Markdown sampled success counts and means with explicit denominators.

    Failed entry attempts retain their statuses and executed partial costs in
    the table, and are excluded from every completed-solution mean.
    """
    if not isinstance(method, WorkspaceMethod):
        raise TypeError("method must be a WorkspaceMethod")
    applications = tuple(applications)
    if any(not isinstance(application, WorkspaceMethodApplication) for application in applications):
        raise TypeError("applications must be WorkspaceMethodApplication records")
    words = (None,) * len(applications) if scrambles is None else tuple(scrambles)
    if len(words) != len(applications):
        raise ValueError("scrambles and applications must have equal lengths")
    solved, rows = [], []
    for number, (word, application) in enumerate(zip(words, applications), 1):
        complete = application.status == "solved" and application.state.is_solved
        entry_word = _simplified_moves(" ".join(step.turn_sequence
                                                for step in application.entry_steps).split())
        entry_htm = len(entry_word.split())
        suffix_htm = (len(application.suffix_application.turn_sequence.split())
                      if application.suffix_application is not None else None)
        full_htm = len(application.turn_sequence.split())
        if complete:
            solved.append((entry_htm, suffix_htm or 0, full_htm))
        rows.append((number, _word(word) if word is not None else "—", application.status,
                     entry_htm, suffix_htm if suffix_htm is not None else "—", full_htm,
                     application.reason or "—"))
    statuses = Counter(application.status for application in applications)
    lines = [f"Solved **{len(solved)} / {len(applications)}** sampled inputs. "
             "Coverage scope: bounded constructive entry followed by a certified continuation. "
             "These inputs do not establish complete scramble coverage.", "",
             "Attempt statuses: " + (", ".join(f"{status}: {count}"
                                              for status, count in sorted(statuses.items())) or "none") + "."]
    if solved:
        means = [float(Fraction(sum(record[index] for record in solved), len(solved)))
                 for index in range(3)]
        lines.extend(["", f"Means over the **{len(solved)} completed solutions**: entry "
                      f"**{means[0]:.2f} HTM**, continuation **{means[1]:.2f} HTM**, "
                      f"concatenated complete execution **{means[2]:.2f} HTM**. "
                      "Each segment is simplified separately; the complete word may cancel "
                      "additional moves at the entry/continuation boundary."])
    else:
        lines.extend(["", "No completed solutions; completed-solution means are undefined."])
    lines.extend(["", "Failed attempts show only their executed partial word lengths. "
                  "They are excluded from completed-solution means.", "",
                  _table(("Input", "Fixture scramble", "Status", "Entry HTM", "Continuation HTM",
                          "Executed complete/partial HTM", "Reason"), rows)])
    return "\n".join(lines)


def method_application_diagram(method, application, *, step_index=None, **draw_options):
    """Physical before/after views, or an overview of actual trace endpoints.

    ``step_index`` is zero-based over executed entry and continuation steps.
    Without it, show the input, completed-entry endpoint and final state,
    omitting adjacent duplicates. The returned Figure can be displayed in a
    notebook; no states or recognition observations are synthesized.
    """
    from .graphics import draw_cubes

    _, entry_steps, suffix_steps = _application_parts(method, application)
    steps = (*entry_steps, *suffix_steps)
    if step_index is not None:
        if type(step_index) is not int or not 0 <= step_index < len(steps):
            raise ValueError("step_index is outside the executed trace")
        step = steps[step_index]
        states, labels = [step.before, step.after], ["Before correction", "After correction"]
    else:
        states, labels = [], []
        endpoints = [(steps[0].before if steps else application.state, "Input")]
        if entry_steps:
            endpoints.append((entry_steps[-1].after, "After entry"))
        endpoints.append((application.state, "Final state"))
        for state, label in endpoints:
            if states and state == states[-1]:
                labels[-1] += " / " + label
            else:
                states.append(state)
                labels.append(label)
    options = {"colors": True, "views": ("UFR", "BLD"), "ncol": 2, "size": 3}
    options.update(draw_options)
    figure = draw_cubes(states, **options)
    views = options.get("views")
    view_count = 1 if views is None or isinstance(views, str) else len(views)
    for index, axis in enumerate(figure.axes):
        if index // view_count < len(labels):
            prior = axis.get_title()
            axis.set_title(labels[index // view_count] + (" · " + prior if prior else ""))
    figure.subplots_adjust(hspace=0.2)
    return figure
