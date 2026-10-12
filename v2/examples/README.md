# Example notebooks

Choose the `v2/.venv` notebook kernel. Each method folder uses puzzle names as
filenames; a puzzle appears only where an example is available.

| Approach | Folder | Contents |
| --- | --- | --- |
| Standard staged solutions | [stabilizer-chain-methods](stabilizer-chain-methods/) | Original piece-by-piece stabilizer chains, reusable corrections and recognition diagrams. |
| Action-family methods | [action-family-methods](action-family-methods/) | Stages discovered from witnessed operations, their endpoint effects and small remaining action families. |
| Optimal colored search | [optimal-colored-search](optimal-colored-search/) | Complete shortest-path distance statistics for small reachable colored-state components. |

## Puzzles

| Puzzle | Stabilizer chain | Action families | Optimal search |
| --- | --- | --- | --- |
| Alcatraz | [Guide](stabilizer-chain-methods/Alcatraz.ipynb) | [Guide](action-family-methods/Alcatraz.ipynb) | — |
| Unbandaged 3×3 | [Guide](stabilizer-chain-methods/Unbandaged3x3.ipynb) | [Guide](action-family-methods/Unbandaged3x3.ipynb) | — |
| Bicube Fuse | [Guide](stabilizer-chain-methods/BicubeFuse.ipynb) | — | [Distance statistics](optimal-colored-search/BicubeFuse.ipynb) |
| Bicube | [Guide](stabilizer-chain-methods/Bicube.ipynb) | — | — |
| Bandaged Pocket Cube | [Guide](stabilizer-chain-methods/BandagedPocketCube.ipynb) | — | — |
| Belt Road | [Guide](stabilizer-chain-methods/BeltRoad.ipynb) | — | — |
| Block Clock Pair | [Guide](stabilizer-chain-methods/BlockClockPair.ipynb) | — | — |
| Diamond Cube | [Guide](stabilizer-chain-methods/DiamondCube.ipynb) | — | — |
| Four Pair | [Guide](stabilizer-chain-methods/FourPair.ipynb) | — | — |
| Most Signatures Cube | [Guide](stabilizer-chain-methods/MostSignaturesCube.ipynb) | — | — |

The action-family notebooks keep only bandage input and guide generation.
The optimal-search notebook counts distinct colored scramble states at each
optimal HTM/QTM distance, including changing shapes. Its complete distance
distribution makes no human-method claim.

The broader [Alcatraz analyses](AlcatrazAnalyses.ipynb),
[Most Signatures Cube analysis](MostSignaturesCubeAnalysis.ipynb), and
[Puzzle Signatures atlas](PuzzleSignatures.ipynb) remain here as research
notebooks. Experiments and acceptance checks for the compact methods live in
[`v2/research`](../research/).
