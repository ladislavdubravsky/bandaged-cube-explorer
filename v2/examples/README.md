# Example notebooks

Choose the `v2/.venv` notebook kernel. Each method folder uses puzzle names as
filenames; a puzzle appears only where an example is available.

| Approach | Folder | Contents |
| --- | --- | --- |
| Standard staged solutions | [stabilizer-chain-methods](stabilizer-chain-methods/) | Original piece-by-piece stabilizer chains, reusable corrections and recognition diagrams. |
| Action-family methods | [action-family-methods](action-family-methods/) | Stages discovered from witnessed operations, their endpoint effects and small remaining action families. |
| Bandage shape navigation | [shapes-graph-navigation](shapes-graph-navigation/) | Input a scrambled shape, obtain its shortest return to the reference shape and optionally draw the shape graph. |
| Optimal colored search | [optimal-colored-search](optimal-colored-search/) | Complete shortest-path distance statistics for small reachable colored-state components. |

## Puzzles

| Puzzle | Stabilizer chain | Action families | Shape navigation | Optimal search |
| --- | --- | --- | --- | --- |
| Alcatraz | [Guide](stabilizer-chain-methods/Alcatraz.ipynb) | [Guide](action-family-methods/Alcatraz.ipynb) | [Shortest return](shapes-graph-navigation/Alcatraz.ipynb) | — |
| Unbandaged 3×3 | [Guide](stabilizer-chain-methods/Unbandaged3x3.ipynb) | [Guide](action-family-methods/Unbandaged3x3.ipynb) | [Single shape](shapes-graph-navigation/Unbandaged3x3.ipynb) | — |
| Bicube Fuse | [Guide](stabilizer-chain-methods/BicubeFuse.ipynb) | — | [Shortest return](shapes-graph-navigation/BicubeFuse.ipynb) | [Distance statistics](optimal-colored-search/BicubeFuse.ipynb) |
| Bicube | [Guide](stabilizer-chain-methods/Bicube.ipynb) | — | [Shortest return](shapes-graph-navigation/Bicube.ipynb) | — |
| Bandaged Pocket Cube | [Guide](stabilizer-chain-methods/BandagedPocketCube.ipynb) | — | [Shortest return](shapes-graph-navigation/BandagedPocketCube.ipynb) | — |
| Belt Road | [Guide](stabilizer-chain-methods/BeltRoad.ipynb) | — | [Shortest return](shapes-graph-navigation/BeltRoad.ipynb) | — |
| Block Clock Pair | [Guide](stabilizer-chain-methods/BlockClockPair.ipynb) | — | [Shortest return](shapes-graph-navigation/BlockClockPair.ipynb) | — |
| Diamond Cube | [Guide](stabilizer-chain-methods/DiamondCube.ipynb) | — | [Shortest return](shapes-graph-navigation/DiamondCube.ipynb) | — |
| Four Pair | [Guide](stabilizer-chain-methods/FourPair.ipynb) | — | [Shortest return](shapes-graph-navigation/FourPair.ipynb) | — |
| Most Signatures Cube | [Guide](stabilizer-chain-methods/MostSignaturesCube.ipynb) | — | [Shortest return](shapes-graph-navigation/MostSignaturesCube.ipynb) | — |

Every notebook in these subfolders ends with a tiny cell that prints a legal
random scramble for its puzzle. Rerun that cell for another scramble. The
public generator also accepts `length` and a reproducible `seed`; see
[the Python interface](../python/README.md#generate-a-legal-scramble).

The action-family notebooks keep bandage input, guide generation and that
final scramble cell.
The shape-navigation notebooks accept observed block labels independently of
scramble history. Their complete HTM shape searches restore the reference
bandage shape, after which a reference-shape method can solve the colors.
Optional drawings use bounded local neighborhoods by default.
The optimal-search notebook counts distinct colored scramble states at each
optimal HTM/QTM distance, including changing shapes. Its complete distance
distribution makes no human-method claim.

The broader [Alcatraz analyses](AlcatrazAnalyses.ipynb),
[Most Signatures Cube analysis](MostSignaturesCubeAnalysis.ipynb), and
[Puzzle Signatures atlas](PuzzleSignatures.ipynb) remain here as research
notebooks. Experiments and acceptance checks for the compact methods live in
[`v2/research`](../research/).
