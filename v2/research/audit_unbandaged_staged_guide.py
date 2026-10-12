#!/usr/bin/env python3
"""Extract exact costs from the saved Unbandaged3x3 notebook guide output.

This reads the notebook without changing it. Case words include the identity
case, so the reported means retain the uniform-group additive cost convention.
"""

import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path


def main():
    base = Path(__file__).resolve().parents[1]
    source = base / "examples/stabilizer-chain-methods/Unbandaged3x3.ipynb"
    notebook = json.loads(source.read_text())
    guide = next("".join(output["data"]["text/markdown"])
                 for cell in notebook["cells"] for output in cell.get("outputs", ())
                 if "## Stage 1:" in "".join(output.get("data", {}).get("text/markdown", ())))
    rows, covered = [], set()
    for part in re.split(r"^## Stage ", guide, flags=re.M)[1:]:
        header = part.splitlines()[0]
        match = re.match(r"(\d+): (Solve|Orient|Place) (Corner|Edge) ([URFDLB]+)", header)
        if match is None:
            continue
        number, kind, piece, slot = match.groups()
        cases = re.split(r"^### Case \d+\s*$", part, flags=re.M)[1:]
        costs = []
        for text in cases:
            if re.search(r"^Skip", text, flags=re.M):
                costs.append(0)
                continue
            execution = re.search(r"^Execute `(.+)`\.$", text, flags=re.M)
            if execution is None:
                raise ValueError(f"stage {number} has an unrecognized case instruction")
            costs.append(len(execution.group(1).rsplit(": ", 1)[1].split()))
        declared = re.search(r"This stage has (\d+) exact cases", part)
        assert declared is not None and len(costs) == int(declared.group(1))
        covered.update(slot)
        rows.append(dict(stage=int(number), label=header, action=kind.lower(), piece=piece,
                         slot=slot, case_count=len(costs), costs=costs,
                         mean_htm=float(Fraction(sum(costs), len(costs))), worst_htm=max(costs),
                         geometrically_untouched_faces="".join(f for f in "URFDLB" if f not in covered)))
    macros = [dict(id="M" + match.group(1), turn_sequence=match.group(2),
                   htm=len(match.group(2).split()))
              for match in re.finditer(r"^\| `M(\d+): ([^`]+)` \|", guide, flags=re.M)]
    record = dict(format="bce-v2-notebook-guide-cost-audit", version=1,
                  source="v2/examples/stabilizer-chain-methods/Unbandaged3x3.ipynb",
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  extraction="parsed saved text/markdown guide output; no solver rerun",
                  scope="uniform-reference-group additive HTM before cancellation between stages",
                  stage_count=len(rows), case_count=sum(r["case_count"] for r in rows),
                  mean_htm=float(sum((Fraction(sum(r["costs"]), len(r["costs"])) for r in rows), Fraction())),
                  worst_htm=sum(r["worst_htm"] for r in rows),
                  learned_macro_count_gt4=sum(m["htm"] > 4 for m in macros),
                  displayed_nontrivial_macros=macros, stages=rows)
    path = base / "research-results/unbandaged3x3-current-guide-audit.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: record[key] for key in (
        "source_sha256", "stage_count", "case_count", "mean_htm", "worst_htm", "learned_macro_count_gt4")}))


if __name__ == "__main__":
    main()
