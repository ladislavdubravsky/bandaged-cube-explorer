"""Small batch interface to the same API used in Python research sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import (
    Shape, State, analyze_isotropy, explore, explore_colored, fixture, fixture_names,
    isotropy_loops, load_puzzle, solve_colored, solve_colored_loops,
)


def _state(puzzle: str) -> State:
    path = Path(puzzle)
    if path.is_file():
        return load_puzzle(path)
    return State(fixture(puzzle))


def _method_reference(puzzle: str):
    """Accept shape-only labels, or use a saved puzzle's reference specification."""
    if puzzle.lstrip().startswith("["):
        return Shape(json.loads(puzzle)), None
    path = Path(puzzle)
    if path.is_file():
        record = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(record, list):
            return Shape(record), path
        return load_puzzle(path).specification, path
    return fixture(puzzle), None


def _check_method_paths(input_path, output_path, guide_path):
    """Reject path and inode aliases before synthesis or writing any artifact."""
    paths = [(name, path) for name, path in
             (("input", input_path), ("JSON output", output_path), ("guide", guide_path))
             if path is not None]
    for i, (name, path) in enumerate(paths):
        for other_name, other_path in paths[i + 1:]:
            same = path.resolve() == other_path.resolve()
            if path.exists() and other_path.exists():
                same = same or path.samefile(other_path)
            if same:
                raise ValueError(f"{name} and {other_name} must be different files")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bce-v2", description="Explore and solve bandaged cube shapes and colored states."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fixtures", help="list bundled puzzle names")
    method = commands.add_parser("plan-method", help="generate a reusable method from a reference shape")
    method.add_argument("puzzle", help="bundled name, inline JSON labels, label-list JSON file, or puzzle JSON file")
    method.add_argument("--strategy", choices=("placement_then_orientation", "fully_solve_each_block"),
                        default="placement_then_orientation")
    method.add_argument("--max-group-elements", type=int, default=None,
                        help="optional preflight bound on the exact reference-group order")
    method.add_argument("--gap-executable", default="gap", help="GAP executable path")
    method.add_argument("--timeout", type=float, default=None, help="maximum seconds per GAP subprocess")
    method.add_argument("--output", type=Path, help="write the complete method JSON; also printed to stdout")
    method.add_argument("--guide", type=Path, help="write the method guide as Markdown")

    for command in ("inspect", "replay", "explore", "solve", "render", "solve-colored", "explore-colored", "isotropy", "solve-loops"):
        sub = commands.add_parser(command)
        sub.add_argument("puzzle", help="bundled name or versioned puzzle JSON file")
        if command in ("replay", "solve"):
            sub.add_argument("moves", help="standard move sequence, for example 'F R2'")
        elif command in ("solve-colored", "solve-loops"):
            sub.add_argument("moves", nargs="?", default="", help="optional legal scramble")
        if command == "solve-colored":
            sub.add_argument("--algorithm", choices=("bfs", "bidirectional"), default="bidirectional")
            sub.add_argument("--max-depth", type=int, default=None)
            sub.add_argument("--target", help="optional target fixture or puzzle JSON file")
        elif command in ("inspect", "render", "explore-colored"):
            sub.add_argument("--moves", default="")
        if command in ("explore", "solve", "solve-colored", "explore-colored", "solve-loops"):
            sub.add_argument("--metric", type=str.upper, choices=("QTM", "HTM"), default="QTM")
        if command == "explore":
            sub.add_argument("--max-vertices", type=int, default=None)
            sub.add_argument("--output", type=Path, help="write a deterministic graph JSON export")
        if command in ("solve-colored", "explore-colored"):
            sub.add_argument("--max-states", type=int, default=None)
        if command == "explore-colored":
            sub.add_argument("--output", type=Path, help="write a colored graph JSON export")
        if command == "render":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--alpha", type=float, default=1.0)
        if command in ("isotropy", "solve-loops"):
            sub.add_argument("--gap-executable", default="gap", help="GAP executable path")
            sub.add_argument("--timeout", type=float, default=None,
                             help="maximum seconds for the GAP subprocess")
        if command == "isotropy":
            sub.add_argument("--loops-only", action="store_true",
                             help="extract complete loop generators without running GAP")
            sub.add_argument("--output", type=Path, help="write deterministic isotropy JSON")
        if command == "solve-loops":
            sub.add_argument("--factorization", choices=("sticker", "quotient_kernel"),
                             default=None, help="factor stickers directly or place blocks then correct rotations")
            sub.add_argument("--max-expanded-moves", type=int, default=None,
                             help="cap unsimplified QTM expansion while retaining the loop expression")
            sub.add_argument("--output", type=Path, help="write the structured loop solution JSON")

    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        arguments = sys.argv[1:] if argv is None else argv
        if error.code == 2 and arguments and arguments[0] == "plan-method":
            return 1
        raise
    try:
        if args.command == "fixtures":
            print("\n".join(fixture_names()))
            return 0

        if args.command == "plan-method":
            from . import synthesize_human_method

            reference, input_path = _method_reference(args.puzzle)
            _check_method_paths(input_path, args.output, args.guide)
            method = synthesize_human_method(
                reference, strategy=args.strategy, max_group_elements=args.max_group_elements,
                gap_executable=args.gap_executable, timeout=args.timeout)
            result = method.to_dict()
            if args.output is not None:
                method.save(args.output)
            if args.guide is not None:
                method.write_guide(args.guide)
            print(json.dumps(result, sort_keys=True))
            return {"completed": 0, "limit_reached": 2}[method.status]

        state = _state(args.puzzle)
        if args.command in ("inspect", "replay", "render", "solve", "solve-colored", "explore-colored", "solve-loops"):
            state = state.apply(args.moves)

        if args.command in ("inspect", "replay"):
            result = {
                "shape": state.shape.labels,
                "corners": state.corners,
                "twists": state.twists,
                "edges": state.edges,
                "flips": state.flips,
                "facelets": state.facelets,
                "legal_moves": state.legal_moves,
                "colored_solved": state.is_solved,
            }
        elif args.command == "explore":
            graph = explore(state.shape, metric=args.metric, max_vertices=args.max_vertices)
            if args.output is not None:
                graph.save(args.output)
            result = {
                "shapes": len(graph),
                "arcs": len(graph.arcs),
                "metric": graph.metric,
                "complete": graph.complete,
            }
            print(json.dumps(result, sort_keys=True))
            return 0 if graph.complete else 2
        elif args.command == "explore-colored":
            graph = explore_colored(state, metric=args.metric, max_states=args.max_states)
            if args.output is not None:
                graph.save(args.output)
            result = {"states": len(graph), "arcs": len(graph.arcs),
                      "metric": graph.metric, "complete": graph.complete}
            print(json.dumps(result, sort_keys=True))
            return 0 if graph.complete else 2
        elif args.command == "solve-colored":
            result = solve_colored(
                state, target=None if args.target is None else _state(args.target),
                metric=args.metric, algorithm=args.algorithm,
                max_states=args.max_states, max_depth=args.max_depth)
            print(json.dumps(result.to_dict(), sort_keys=True))
            return {"solved": 0, "limit_reached": 2, "unreachable": 3}[result.status]
        elif args.command == "solve-loops":
            factorization_options = ({"factorization": args.factorization}
                                     if args.factorization is not None else {})
            solution = solve_colored_loops(
                state, metric=args.metric, gap_executable=args.gap_executable,
                timeout=args.timeout, max_expanded_moves=args.max_expanded_moves,
                **factorization_options)
            result = solution.to_dict()
            if args.output is not None:
                args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
            print(json.dumps(result, sort_keys=True))
            return {"solved": 0, "limit_reached": 2, "unreachable": 3}[solution.status]
        elif args.command == "solve":
            graph = explore(state.specification, metric=args.metric)
            solution = graph.shortest_path(state.shape, state.specification)
            result = {
                "shape_solution": solution,
                "metric": graph.metric,
                "colored_solved_after": state.apply(solution).is_solved,
            }
        elif args.command == "isotropy":
            if args.loops_only:
                result = isotropy_loops(state).to_dict(include_moves=True)
            else:
                result = analyze_isotropy(
                    state, gap_executable=args.gap_executable,
                    timeout=args.timeout).to_dict(include_moves=True)
            if args.output is not None:
                args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        else:
            from .graphics import draw_cubes

            figure = draw_cubes(state.shape, alpha=args.alpha)
            figure.savefig(args.output)
            return 0
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, ImportError, RuntimeError) as error:
        print(f"bce-v2: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
