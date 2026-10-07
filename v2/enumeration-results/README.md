# Complete shell puzzle enumeration

The 6 October 2026 run classifies every connected cuboid-footprint partition of
the 26-cell shell. The virtual core is an independent ghost. Equivalence includes
legal outer-face motion, the 24 proper rotations, and exact implicit adjacent-
bond closure. Both the original atlas and a filtered atlas are retained.

| Atlas | Classes | Additional equivalence/filter |
| --- | ---: | --- |
| [Original](2026-10-06-shell-puzzles.csv) | 7,073 | Mirror images and dead ends retained |
| [Filtered](2026-10-06-shell-puzzles-no-mirrors-or-dead-ends.csv) | **4,857** | Mirror pairs identified; frozen and permanently one-axis puzzles excluded |

Block inventories are stored in the derived
[signature database](2026-10-07-shell-signatures.sqlite3), with all four atlas
cohorts, exact physical block records, and stable puzzle IDs. The
[signature CSV](2026-10-07-shell-signatures.csv) lists all **931** dimension
signatures and their puzzle counts; **928** occur in the filtered atlas.
The [signature manifest](2026-10-07-shell-signatures.json) records provenance
and checksums. Explore counts, exact inventories, maximum-domino puzzles, and
galleries in [PuzzleSignatures.ipynb](../examples/PuzzleSignatures.ipynb).
See [definitions and the omitted-core distinction](../../docs/block-signatures.md).

The mirror quotient alone has 4,860 classes: 2,647 classes equivalent to their
own mirrors and 2,213 mirror pairs. The mobility filter removes exactly three:
the fused shell, a full face attached to a thickness-two slab, and three full
slabs. It checks all reachable shapes, retaining puzzles that later unlock
another axis. The unbandaged cube is retained.

[Mirror analysis](2026-10-06-shell-mirror-analysis.json) records all filter counts,
timing, filenames, and checksums. The [partner map](2026-10-06-shell-mirror-pairs.csv)
records every original class's mirror ID, closed component size, proper-rotation
shape count, and faces/axes ever turnable. Mirror partners were found by reflecting
every reachable shape, with existence and involution checked for all 7,073
classes. Analysis took 33.687 seconds and visited 7,858,798 closed vertices.

The [independent validation report](2026-10-06-shell-mirror-validation.json)
checks all pair records, all four filter totals, every filtered row against the
source, and the three dataset checksums. Twelve complete component checks also
reproduce mirror IDs with independent coordinate reflection and rotation
geometry, including separate exploration of reflected components.

[shell-puzzles.csv](2026-10-06-shell-puzzles.csv) contains one representative per
behavioral class, sorted by its stable AxisMajor hexadecimal key. The first
line declares the model and completeness. Each row retains the representative
labels, originating seed labels, and that seed's raw fixed-frame component size.
The [summary](2026-10-06-shell-summary.json) records coverage, counts before and
after implicit closure, timing, memory, and the CSV checksum.

Load or render representatives without additional data dependencies:

```python
import csv
from pathlib import Path
import bce_v2 as c

path = Path("v2/enumeration-results/2026-10-06-shell-puzzles-no-mirrors-or-dead-ends.csv")
with path.open() as stream:
    records = list(csv.DictReader(line for line in stream if not line.startswith("#")))
puzzles = [c.Shape([int(x) for x in row["representative_labels"].split()])
           for row in records]
c.draw_cubes(puzzles[:12])
```

Class IDs are meaningful together with the declared equivalence and core model.
To reconstruct an originating seed's transformation, explore `seed_labels`,
close its component, and find a shortest shape path to a rotated representative.
The closure preserves that path's legality and original cubie transports.

The exhaustive output was checked independently for unique sorted IDs,
canonical labels, rotation minima, shell connectivity, cuboid footprints, and
recursive full-plane slicing. Global seed and geometric-orbit coverage match
independent exact-cover and Burnside totals. See [the research and proofs](../../docs/enumeration.md)
and [timing evidence](../benchmark-results/enumeration.md).

Reproduce from `v2/`:

```sh
cargo run --release --bin enumerate -- scan --implicit-bonds --output /tmp/shell-puzzles.csv
cargo run --release --bin analyze_atlas -- enumeration-results/2026-10-06-shell-puzzles.csv --dead-ends one-axis --output /tmp/filtered-puzzles.csv --summary /tmp/mirror-analysis.json --pairs /tmp/mirror-pairs.csv
```

Validate the retained files from the repository root:

```sh
v2/.venv/bin/python v2/research/validate_enumeration.py v2/enumeration-results/2026-10-06-shell-puzzles.csv
v2/.venv/bin/python v2/research/validate_mirror_analysis.py v2/enumeration-results/2026-10-06-shell-mirror-analysis.json
v2/.venv/bin/python v2/research/build_signature_database.py
```
