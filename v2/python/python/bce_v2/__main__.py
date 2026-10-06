"""Small batch interface to the same API used in Python research sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import State, explore, fixture, fixture_names, load_puzzle


def _state(puzzle: str) -> State:
    path = Path(puzzle)
    if path.is_file():
        return load_puzzle(path)
    return State(fixture(puzzle))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bce-v2", description="Explore bandaged cube shapes with standard face moves."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fixtures", help="list bundled puzzle names")

    for command in ("inspect", "replay", "explore", "solve", "render"):
        sub = commands.add_parser(command)
        sub.add_argument("puzzle", help="bundled name or versioned puzzle JSON file")
        if command in ("replay", "solve"):
            sub.add_argument("moves", help="standard move sequence, for example 'F R2'")
        elif command in ("inspect", "render"):
            sub.add_argument("--moves", default="")
        if command in ("explore", "solve"):
            sub.add_argument("--metric", type=str.upper, choices=("QTM", "HTM"), default="QTM")
        if command == "explore":
            sub.add_argument("--max-vertices", type=int, default=None)
            sub.add_argument("--output", type=Path, help="write a deterministic graph JSON export")
        if command == "render":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--alpha", type=float, default=1.0)

    args = parser.parse_args(argv)
    try:
        if args.command == "fixtures":
            print("\n".join(fixture_names()))
            return 0

        state = _state(args.puzzle)
        if args.command in ("inspect", "replay", "render", "solve"):
            state = state.apply(args.moves)

        if args.command in ("inspect", "replay"):
            result = {
                "shape": state.shape.labels,
                "corners": state.corners,
                "twists": state.twists,
                "edges": state.edges,
                "flips": state.flips,
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
        elif args.command == "solve":
            graph = explore(state.specification, metric=args.metric)
            solution = graph.shortest_path(state.shape, state.specification)
            result = {
                "shape_solution": solution,
                "metric": graph.metric,
                "colored_solved_after": state.apply(solution).is_solved,
            }
        else:
            from .graphics import draw_cubes

            figure = draw_cubes(state.shape, alpha=args.alpha)
            figure.savefig(args.output)
            return 0
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, ImportError) as error:
        print(f"bce-v2: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
