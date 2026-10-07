# Block signatures of puzzle classes

7 October 2026. [PuzzleSignatures.ipynb](../v2/examples/PuzzleSignatures.ipynb)
explores the complete class atlas by block inventory, with saved tables and
galleries. Select the `v2/.venv` kernel. Its default cohort is the 4,857-class
atlas identifying mirrors and excluding permanently frozen or one-axis puzzles;
change `COHORT` to `"all"` for all 7,073 classes.

## Types and signatures

A block type gives its sorted box dimensions **and** its center/core placement.
The catalogue has fifteen shell types and two additional core-enabled types.
All singleton cubies remain 111, as requested; only larger blocks are split.

| Type | Dimensions | Physical shell cubies | Meaning |
| --- | --- | ---: | --- |
| `333` | 3×3×3 | 26 | Fully fused shell |
| `332` | 3×3×2 | 17 | Two fused layers |
| `322` | 3×2×2 | 11 | BigBlock |
| `331` | 3×3×1 | 9 | Outer layer; one center |
| `331Core` | 3×3×1 | 8 | Middle layer; four centers |
| `222` | 2×2×2 | 7 | Corner box with the core omitted |
| `321` | 3×2×1 | 6 | Outer rectangle; one center |
| `321Core` | 3×2×1 | 5 | Middle rectangle; three centers |
| `221` | 2×2×1 | 4 | Outer rectangle; one center |
| `221Core` | 2×2×1 | 3 | Middle rectangle; two centers |
| `311` | 3×1×1 | 3 | Straight bar without a center |
| `BigClock` | 3×1×1 | 3 | Straight bar through one center |
| `311Core` | 3×1×1 | Core-enabled only | Two opposite centers joined through the core |
| `Clock` | 2×1×1 | 2 | Contains a face center |
| `Pair` | 2×1×1 | 2 | Contains no face center |
| `211Core` | 2×1×1 | Core-enabled only | One face center joined to the core |
| `111` | 1×1×1 | 1 | Unfused physical cubie |

The signature counts these position-aware nonsingleton types. A count of one has no prefix;
larger multiplicities use `2x221`, for example `2x221 Clock 2xPair`. Types appear
largest first by bounding-box volume, then dimensions. `322` retains its numeric
identifier, while BigBlock is recorded as its name. The unbandaged cube displays
as `111 only`. A query for numeric `211` combines Clock and Pair in the shell
atlas. Other type names match exactly: `221` excludes `221Core`, and `311`
excludes BigClock. SQL queries can use `block_inventory.dimensions` to combine
all variants of a size deliberately.

These are signatures of the **implicitly closed representative**, not its
originating explicit glue recipe. The physical blocks of that representative
move rigidly under every legal turn. Quarter turns and cube symmetries preserve
sorted dimensions and corner/edge/center membership, including the Pair/Clock
distinction. This proves signature invariance throughout each motion class and
between mirror partners. Different puzzle classes can share a signature.

## The omitted core and finer inventories

In this shell model a cuboid means a connected box footprint with the virtual
core omitted. `Core` names distinguish positions whose box contains the core;
they do not enable invisible bonds. Thus 221Core has three physical cubies and
321Core has five. The core-enabled versions have four and six respectively.

222, 322, 332, and 333 each have just one center/core pattern, so their numeric
names remain unchanged despite always enclosing the core position. A shell
projection of 211Core is just a singleton; a shell projection of 311Core is two
disconnected opposite centers. They therefore occur only with core bonds enabled.

These distinctions replace the previous dimension-only grouping. Every larger
type now determines its physical cubie count and composition in the chosen model,
so each signature **does imply** the number of remaining 111 cubies. Grouped
results expose this as `singletons`; minimum and maximum checks always agree.
The ghost core itself is never counted as a shell singleton.

Every block also stores its actual cubie count, corner count, edge count, center
count, actual core count, and core-hole flag. The detailed signature groups these
records by `(type, cubies, corners, edges, centers, cores, core_hole)`, retaining
multiplicities, including singleton kinds. No further signature distinctions arise
in this atlas: remaining singleton kinds follow from the larger blocks.

| Inventory model | All classes | Filtered classes |
| --- | ---: | ---: |
| Puzzle classes | 7,073 | 4,857 |
| Position-aware signatures, omitting 111 | 1,735 | 1,732 |
| Position-aware signatures plus exact 111 count | 1,735 | 1,732 |
| Detailed cubie-kind signatures | 1,735 | 1,732 |

Mirror identification preserves the set of signatures. Removing the three
dead-end puzzles removes three signatures. No filtered puzzle contains `333`,
`332`, `331`, or `331Core` after implicit closure.

## Example answers

Among puzzles made only of `211` blocks and `111` cubies, the maximum number of
`211` blocks **per puzzle** is **12** in both cohorts. The following table counts
**puzzle classes** satisfying each condition:

| Condition | All classes | Filtered classes |
| --- | ---: | ---: |
| Contain at least one 222 | 339 | 238 |
| Contain twelve 211 blocks, with only 111 cubies remaining | 2 | 1 |

The maximum-domino puzzles have signature `5xClock 7xPair`, with two remaining
111 cubies. The two full-atlas classes (`0000100071df00` and `0000100073de00`)
are a mirror pair. Twelve is an independent geometric upper bound: every shell
domino contains one of the twelve edge cubies and one corner or center. The
atlas supplies the attainable maximum among behavioral classes.

## Stored data and queries

The [SQLite database](../v2/enumeration-results/2026-10-07-shell-signatures.sqlite3)
contains one puzzle record per original class, individual physical block
records, a type catalogue, and provenance metadata. Its views are `puzzles_all`,
`puzzles_mirror`, `puzzles_mobile`, and `puzzles_filtered`. `block_inventory`
joins block dimensions and names; `signature_totals` groups all four cohorts.
The original certified CSVs and checksums remain unchanged.

The [complete signature CSV](../v2/enumeration-results/2026-10-07-shell-signatures.csv)
lists every human-readable signature, machine-readable counts, puzzle totals for
all four cohorts, and implied singleton counts. The [manifest](../v2/enumeration-results/2026-10-07-shell-signatures.json)
records file checksums, source provenance, definitions, cohort totals, and
verification counts. The notebook displays every signature in the selected
cohort in a scrollable table; no rows are truncated.

```python
from pathlib import Path
import bce_v2 as c

database = Path("v2/enumeration-results/2026-10-07-shell-signatures.sqlite3")
with c.PuzzleAtlas(database, cohort="filtered") as atlas:
    containing_222 = atlas.containing("222")
    maximum, puzzles = atlas.maximum("211", only=("211",))
    exact = atlas.select(signature=c.format_signature({"221": 2, "Clock": 1, "Pair": 2}))
    combined = atlas.select(contains={"Clock": 2, "Pair": 2}, only=("211",))
    every_signature = atlas.signature_counts()
    example = atlas.shape(puzzles[0]["id"])
    inventory = c.block_signature(example, include_singletons=True)
```

`only` always allows remaining 111 cubies. `maximum` means the global largest
count in the selected candidate family, rather than an arrangement to which no
more bandaging can be added. `classify_blocks` exposes immutable physical block
records, rejecting noncuboid footprints and undeclared core bonds. `PuzzleAtlas`
opens SQLite read-only and also accepts custom parameterized SQL through `query`.

Rebuild all derived artifacts from the repository root:

```sh
v2/.venv/bin/python v2/research/build_signature_database.py
v2/.venv/bin/python -m unittest discover -s v2/python/tests -p test_signatures.py -v
```

Generation verifies the certified source checksums, all class identifiers,
filtered membership, 26/8/12/6 physical cubie/corner/edge/center totals, and exact
inventory agreement for every mirror partner. It also checks the full inventory
after all 16,013 legal clockwise successors of saved representatives. Regression
tests cover core-hole variants, all spatial rotations, an independent coordinate
reflection, legal walks, aggregate query answers, every persisted inventory,
and SQLite integrity and foreign keys. An exhaustive catalogue test covers all
206 admitted shell footprints and all 216 full-grid boxes, confirming that every
nonsingleton type is one spatial block orbit under proper rotations. Schema
version two prevents older dimension-only databases from being used silently.

## Follow-up questions

- Which signatures admit the most distinct arrangements? What geometric features
  distinguish classes sharing the same inventory?
- How widely does mobility vary within a signature, including unlocking distance
  and the number of reachable shapes? Shape counts alone do not measure colored
  solving difficulty.
- Which signatures admit only self-mirror classes, only chiral pairs, or both?
- How differently do 221 and 221Core, 321 and 321Core, or 311 and BigClock affect
  mobility and possible inventories?
- Which inventories are impossible from cubie counts or packing constraints,
  before considering implicit closure and legal-turn equivalence?
- How do minimal explicit glue recipes differ from the effective block signature
  after all implicit bonds merge?
