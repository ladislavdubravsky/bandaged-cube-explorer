# Reference-shape solving method

This computational baseline covers all **324 reachable colored states** whose bandage shape is already the declared reference shape.

The stage policies and physical algorithms have been checked exhaustively. Human memorability and ease of execution have not been reviewed; some algorithms may be long.

## Before starting

Restore the reference bandage shape first. Shape restoration is separate work. Keep the fixed U/R/F/D/L/B face frame throughout the method.

Identify each colored block by its reference member cells and color pattern. A cell name such as UFR means the upper, front, right corner; UF means the upper front edge. A fused block name lists all of its reference member cells.

A sticker label such as `UFR/U` means the U-face-colored sticker on the reference UFR cubie. An orientation cue such as `UFR/U → UBR/R` says that this same colored sticker is currently on the R face at the UBR corner. Use the reference color scheme to identify it.

Follow the stages in order. At each stage inspect only its named block, match the case, and execute the listed algorithm completely. A solved case needs no moves.

Algorithms may disturb earlier solved blocks and the reference shape internally. They restore both at the end of the whole correction. Make the next case decision only then.

Blocks already forced to be solved in this reference shape: 221 UBL-UB-UL-U; 222 BL-B-L-C-DBL-DB-DL-D; Clock R-DR; Clock F-DF.

## Stage 1: Solve Edge UR

There are 4 cases. This stage reduces the remaining possibilities from 324 to 81.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `UR` | `UR/U → UR/U` | 0 (mod 2) | Skip — already correct |
| `UR` | `UR/U → UR/R` | 1 (mod 2) | `A1` |
| `UF` | `UR/U → UF/U` | 0 (mod 2) | `A2` |
| `UF` | `UR/U → UF/F` | 1 (mod 2) | `A3` |

Phase is a coordinate modulo 2 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

Also correct automatically after this stage: place Edge UR; place Edge UF; fully solve Edge UF.

## Stage 2: Solve Corner UFR

There are 9 cases. This stage reduces the remaining possibilities from 81 to 9.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `UBR` | `UFR/U → UBR/U` | 0 (mod 3) | `A4` |
| `UBR` | `UFR/U → UBR/B` | 1 (mod 3) | `A5` |
| `UBR` | `UFR/U → UBR/R` | 2 (mod 3) | `A6` |
| `UFL` | `UFR/U → UFL/U` | 0 (mod 3) | `A7` |
| `UFL` | `UFR/U → UFL/F` | 1 (mod 3) | `A8` |
| `UFL` | `UFR/U → UFL/L` | 2 (mod 3) | `A9` |
| `UFR` | `UFR/U → UFR/U` | 0 (mod 3) | Skip — already correct |
| `UFR` | `UFR/U → UFR/R` | 1 (mod 3) | `A10` |
| `UFR` | `UFR/U → UFR/F` | 2 (mod 3) | `A11` |

Phase is a coordinate modulo 3 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

Also correct automatically after this stage: place Corner UBR; place Corner UFL; place Corner UFR.

## Stage 3: Orient Corner UBR

There are 3 cases. This stage reduces the remaining possibilities from 9 to 3.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `UBR` | `UBR/U → UBR/U` | 0 (mod 3) | Skip — already correct |
| `UBR` | `UBR/U → UBR/B` | 1 (mod 3) | `A12` |
| `UBR` | `UBR/U → UBR/R` | 2 (mod 3) | `A13` |

Phase is a coordinate modulo 3 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

Also correct automatically after this stage: fully solve Corner UFL.

## Stage 4: Solve Pair BR-DBR

There are 3 cases. This stage reduces the remaining possibilities from 3 to 1.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `BR-DBR` | `BR/R → BR/R` | 0 (mod 1) | Skip — already correct |
| `FL-DFL` | `BR/R → FL/L` | 0 (mod 1) | `A14` |
| `FR-DFR` | `BR/R → FR/F` | 0 (mod 1) | `A15` |

Phase is a coordinate modulo 1 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

Also correct automatically after this stage: place Pair BR-DBR; place Pair FL-DFL; place Pair FR-DFR; fully solve Pair FL-DFL; fully solve Pair FR-DFR.

## Shared correction algorithms

Singmaster notation uses U/R/F/D/L/B face turns, an apostrophe for the inverse, and 2 for a half turn. Execute each complete expanded word below.

Expressions retain original-loop provenance. `[A, B]` means A B A⁻¹ B⁻¹; `conj(S, A)` means S A S⁻¹. A power repeats the enclosed word. The expanded face turns are authoritative for execution.

### A1

10 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L142)^-1`

```text
U F' U' F2 R' F' R2 U' R' U
```

### A2

11 face turns (HTM), 16 quarter turns (QTM).

Expression: `L171`

```text
R2 F2 R2 F U F2 U' F2 U F U'
```

### A3

10 face turns (HTM), 14 quarter turns (QTM).

Expression: `(L175)^-1`

```text
F R' F R F2 R' F2 R' F2 R2
```

### A4

12 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L662)^-1`

```text
U' R' U F U F' U' R U F U' F'
```

### A5

12 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L732)^-1`

```text
R' U' R U F U' R' U R U F' U'
```

### A6

19 face turns (HTM), 24 quarter turns (QTM).

Expression: `L865^-1 (L175)^-1`

```text
R' F R' F' R U' R2 U R F R F R F2 R' F2 R' F2 R2
```

### A7

12 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L732^-1)^-1`

```text
U F U' R' U' R U F' U' R' U R
```

### A8

13 face turns (HTM), 18 quarter turns (QTM).

Expression: `L342 (L175)^-1`

```text
R' F2 R F U F2 U' F' R' F2 R' F2 R2
```

### A9

12 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L662^-1)^-1`

```text
F U F' U' R' U F U' F' U' R U
```

### A10

19 face turns (HTM), 24 quarter turns (QTM).

Expression: `(L142)^-2`

```text
U F' U' F2 R' F' R2 U' R' U2 F' U' F2 R' F' R2 U' R' U
```

### A11

19 face turns (HTM), 24 quarter turns (QTM).

Expression: `(L142)^2`

```text
U' R U R2 F R F2 U F U2 R U R2 F R F2 U F U'
```

### A12

19 face turns (HTM), 20 quarter turns (QTM).

Expression: `L672 (L732)^-1`

```text
F U F' U2 R' U F R U F' U' F U' R' U R U F' U'
```

### A13

19 face turns (HTM), 20 quarter turns (QTM).

Expression: `(L662)^-1 L672`

```text
U' R' U F U F' U' R U' R' U F R U F' U2 R' U R
```

### A14

12 face turns (HTM), 14 quarter turns (QTM).

Expression: `L612^-1`

```text
R' F R F R2 F' R' U' R2 U F' R
```

### A15

12 face turns (HTM), 14 quarter turns (QTM).

Expression: `L612`

```text
R' F U' R2 U R F R2 F' R' F' R
```

## Original loop definitions

These definitions make every provenance expression self-contained. Each loop starts and ends at the reference shape.

### L142

```text
U' R U R2 F R F2 U F U'
```

### L662

```text
F U F' U' R' U F U' F' U' R U
```

### L732

```text
U F U' R' U' R U F' U' R' U R
```

### L175

```text
R2 F2 R F2 R F2 R' F' R F'
```

### L285

```text
F R2 F' R2 F R U' R2 U F' R
```

### L342

```text
R' F2 R F U F2 U' F R' F' R F'
```

### L612

```text
R' F U' R2 U R F R2 F' R' F' R
```

### L865

```text
F R2 F' R' U' R2 U R' F R F' R
```

### L171

```text
R2 F2 R2 F U F2 U' F2 U F U'
```

### L672

```text
F U F' U2 R' U F R U F' U2 R' U R
```

After the final stage, every modeled corner and edge sticker is solved. Unmarked center spin and independent virtual-core spin are outside this model.
