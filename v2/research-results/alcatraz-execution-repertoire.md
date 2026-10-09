# Reference-shape method with a shared repertoire

This computational method covers all **324 reachable colored states** whose bandage shape is already the declared reference shape.

Every full case route, repeated instruction, and recognition family has been checked. Human memorability and ease of execution await the planned human review.

## Before starting

Restore the reference bandage shape first, and keep the fixed U/R/F/D/L/B face frame. Shape restoration is separate work.

Identify each colored block by its reference cells and color pattern. A name such as UFR denotes the upper, front, right corner; UF denotes the upper front edge. A fused block name lists its reference member cells.

A cue such as `UFR/U → UBR/R` identifies the U-face-colored sticker of the reference UFR cubie, currently on the R face at UBR. Use the reference color scheme to find it.

Follow the stages in order. Match the current footprint or sticker cue, execute the listed instruction completely, and inspect the same stage again. Advance when its solved cue appears. Rank is a progress coordinate: it strictly decreases after each instruction, so repetition terminates.

Make case decisions only at whole-instruction boundaries. A power or setup/body/undo recipe can temporarily disturb earlier solved blocks. Its complete instruction restores them and the reference shape. Do not inspect between repetitions inside a listed power or between pieces of a setup recipe.

Master names such as M1 refer to the shared words below. A negative power executes the inverse word: reverse its turns and invert each turn. `[A, B]` means A B A⁻¹ B⁻¹; `conj(S, A)` means S A S⁻¹. A listed rotation transfers the word through the indicated regrip and undo; its face-only execution is already checked for this bandage. The whole-cube regrips x, y, and z turn the cube in the directions of R, U, and F respectively. `rotate(rho, M)` means regrip by rho, execute M in that frame, then undo the regrip.

Blocks already forced to be solved in this reference shape: 221 UBL-UB-UL-U; 222 BL-B-L-C-DBL-DB-DL-D; Clock R-DR; Clock F-DF.

## Stage 1: Solve Edge UR

This stage has 4 exact cases and 3 instruction families. It reduces the remaining possibilities from 324 to 81.

Find this colored block's footprint and the named reference sticker. The sticker cue distinguishes its observable orientations.

### R1.1

For the following cues, execute `M1` once, then inspect this stage's block again.

| Current cue |
| --- |
| `UF`; `UR/U → UF/F` |

### R1.2

For the following cues, execute `M2` once, then inspect this stage's block again.

| Current cue |
| --- |
| `UR`; `UR/U → UR/R` |

### R1.3

For the following cues, execute `M4` once, then inspect this stage's block again.

| Current cue |
| --- |
| `UF`; `UR/U → UF/U` |

### Complete cue lookup

Use these instructions until the solved case appears. Each row gives the next whole instruction rather than a new word to memorize.

| Current footprint | Reference sticker currently at | Phase | Instruction | Rank |
| --- | --- | --- | --- | ---: |
| `UR` | `UR/U → UR/U` | 0 (mod 2) | Skip — already correct | 0 |
| `UR` | `UR/U → UR/R` | 1 (mod 2) | `M2` | 10 |
| `UF` | `UR/U → UF/U` | 0 (mod 2) | `M4` | 11 |
| `UF` | `UR/U → UF/F` | 1 (mod 2) | `M1` | 10 |

Phase is a coordinate modulo 2 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. Use the concrete sticker cue to choose the instruction; the phase number does not prescribe an independent twist of this block.

Also correct automatically after this stage: place Edge UR; place Edge UF; fully solve Edge UF.

## Stage 2: Solve Corner UFR

This stage has 9 exact cases and 5 instruction families. It reduces the remaining possibilities from 81 to 9.

Find this colored block's footprint and the named reference sticker. The sticker cue distinguishes its observable orientations.

### R2.1

For the following cues, execute `M10` once, then inspect this stage's block again.

| Current cue |
| --- |
| `UFL`; `UFR/U → UFL/F` |

### R2.2

For the following cues, execute `M13` once, then inspect this stage's block again.

| Current cue |
| --- |
| `UBR`; `UFR/U → UBR/R` |

### R2.3

These cases share the master recipe `M2`. Choose its signed power using the block's concrete cue.

| Current cue | Signed power |
| --- | ---: |
| `UFR`; `UFR/U → UFR/R` | 2 |
| `UFR`; `UFR/U → UFR/F` | -2 |

### R2.4

These cases share the master recipe `M7`. Choose its signed power using the block's concrete cue.

| Current cue | Signed power |
| --- | ---: |
| `UBR`; `UFR/U → UBR/U` | -1 |
| `UFL`; `UFR/U → UFL/L` | 1 |

### R2.5

These cases share the master recipe `M9`. Choose its signed power using the block's concrete cue.

| Current cue | Signed power |
| --- | ---: |
| `UBR`; `UFR/U → UBR/B` | 1 |
| `UFL`; `UFR/U → UFL/U` | -1 |

### Complete cue lookup

Use these instructions until the solved case appears. Each row gives the next whole instruction rather than a new word to memorize.

| Current footprint | Reference sticker currently at | Phase | Instruction | Rank |
| --- | --- | --- | --- | ---: |
| `UBR` | `UFR/U → UBR/U` | 0 (mod 3) | `M7^-1` | 12 |
| `UBR` | `UFR/U → UBR/B` | 1 (mod 3) | `M9` | 12 |
| `UBR` | `UFR/U → UBR/R` | 2 (mod 3) | `M13` | 19 |
| `UFL` | `UFR/U → UFL/U` | 0 (mod 3) | `M9^-1` | 12 |
| `UFL` | `UFR/U → UFL/F` | 1 (mod 3) | `M10` | 13 |
| `UFL` | `UFR/U → UFL/L` | 2 (mod 3) | `M7` | 12 |
| `UFR` | `UFR/U → UFR/U` | 0 (mod 3) | Skip — already correct | 0 |
| `UFR` | `UFR/U → UFR/R` | 1 (mod 3) | `M2^2` | 19 |
| `UFR` | `UFR/U → UFR/F` | 2 (mod 3) | `M2^-2` | 19 |

Phase is a coordinate modulo 3 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. Use the concrete sticker cue to choose the instruction; the phase number does not prescribe an independent twist of this block.

Also correct automatically after this stage: place Corner UBR; place Corner UFL; place Corner UFR.

## Stage 3: Orient Corner UBR

This stage has 3 exact cases and 1 instruction family. It reduces the remaining possibilities from 9 to 3.

Find this colored block's footprint and the named reference sticker. The sticker cue distinguishes its observable orientations.

### R3.1

These cases form one cycle under `M14`. Use the signed power below to reach this stage's solved observation.

Cycle in the fixed reference frame: `UBR`; `UBR/U → UBR/U` → `UBR`; `UBR/U → UBR/R` → `UBR`; `UBR/U → UBR/B`.

| Current cue | Signed power |
| --- | ---: |
| `UBR`; `UBR/U → UBR/B` | 1 |
| `UBR`; `UBR/U → UBR/R` | -1 |

### Complete cue lookup

Use these instructions until the solved case appears. Each row gives the next whole instruction rather than a new word to memorize.

| Current footprint | Reference sticker currently at | Phase | Instruction | Rank |
| --- | --- | --- | --- | ---: |
| `UBR` | `UBR/U → UBR/U` | 0 (mod 3) | Skip — already correct | 0 |
| `UBR` | `UBR/U → UBR/B` | 1 (mod 3) | `M14` | 19 |
| `UBR` | `UBR/U → UBR/R` | 2 (mod 3) | `M14^-1` | 19 |

Phase is a coordinate modulo 3 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. Use the concrete sticker cue to choose the instruction; the phase number does not prescribe an independent twist of this block.

Also correct automatically after this stage: fully solve Corner UFL.

## Stage 4: Solve Pair BR-DBR

This stage has 3 exact cases and 1 instruction family. It reduces the remaining possibilities from 3 to 1.

Find this colored block's footprint and the named reference sticker. The sticker cue distinguishes its observable orientations.

### R4.1

These cases form one cycle under `M8`. Use the signed power below to reach this stage's solved observation.

Cycle in the fixed reference frame: `BR-DBR`; `BR/R → BR/R` → `FR-DFR`; `BR/R → FR/F` → `FL-DFL`; `BR/R → FL/L`.

| Current cue | Signed power |
| --- | ---: |
| `FL-DFL`; `BR/R → FL/L` | 1 |
| `FR-DFR`; `BR/R → FR/F` | -1 |

### Complete cue lookup

Use these instructions until the solved case appears. Each row gives the next whole instruction rather than a new word to memorize.

| Current footprint | Reference sticker currently at | Phase | Instruction | Rank |
| --- | --- | --- | --- | ---: |
| `BR-DBR` | `BR/R → BR/R` | 0 (mod 1) | Skip — already correct | 0 |
| `FL-DFL` | `BR/R → FL/L` | 0 (mod 1) | `M8` | 12 |
| `FR-DFR` | `BR/R → FR/F` | 0 (mod 1) | `M8^-1` | 12 |

Phase is a coordinate modulo 1 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. Use the concrete sticker cue to choose the instruction; the phase number does not prescribe an independent twist of this block.

Also correct automatically after this stage: place Pair BR-DBR; place Pair FL-DFL; place Pair FR-DFR; fully solve Pair FL-DFL; fully solve Pair FR-DFR.

## Shared master definitions

Learn these shared words. Singmaster notation uses U/R/F/D/L/B, an apostrophe for an inverse turn, and 2 for a half turn. Each master starts and ends at the reference shape. Its admissibility depends on the complete instruction listed for the current stage.

### M1

10 face turns (HTM), 14 quarter turns (QTM).

```text
F R' F R F2 R' F2 R' F2 R2
```

### M2

10 face turns (HTM), 12 quarter turns (QTM).

```text
U F' U' F2 R' F' R2 U' R' U
```

### M4

11 face turns (HTM), 16 quarter turns (QTM).

```text
R2 F2 R2 F U F2 U' F2 U F U'
```

### M7

12 face turns (HTM), 12 quarter turns (QTM).

```text
F U F' U' R' U F U' F' U' R U
```

### M8

12 face turns (HTM), 14 quarter turns (QTM).

```text
R' F R F R2 F' R' U' R2 U F' R
```

### M9

12 face turns (HTM), 12 quarter turns (QTM).

```text
R' U' R U F U' R' U R U F' U'
```

### M10

13 face turns (HTM), 18 quarter turns (QTM).

```text
R' F2 R F U F2 U' F' R' F2 R' F2 R2
```

### M13

19 face turns (HTM), 24 quarter turns (QTM).

```text
R' F R' F' R U' R2 U R F R F R F2 R' F2 R' F2 R2
```

### M14

19 face turns (HTM), 20 quarter turns (QTM).

```text
R' U' R U2 F U' R' F' U' R U R' U F U' F' U' R U
```

After the final stage every modeled corner and edge sticker is solved. Unmarked center spin and independent virtual-core spin are outside this model.

## Witness provenance

The portable repertoire stores every master's original-loop expression, complete expanded case routes, the generating witness basis, and the original baseline. These records support independent replay and coverage checks; the shared words above are the repertoire used by this guide.

- M1: `(L175)^-1`
- M2: `(L142)^-1`
- M4: `L171`
- M7: `(L662)^1`
- M8: `L612^-1`
- M9: `(L732)^-1`
- M10: `L342 (L175)^-1`
- M13: `L865^-1 (L175)^-1`
- M14: `((L662)^-1 L672)^-1`
