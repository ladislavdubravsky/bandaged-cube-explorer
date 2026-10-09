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

## Stage 1: Place Corner UFR

There are 3 cases. This stage reduces the remaining possibilities from 324 to 108.

Find the footprint occupied by this colored block. Ignore its orientation while choosing the case.

| Current footprint | Correction |
| --- | --- |
| `UBR` | `A1` |
| `UFL` | `A2` |
| `UFR` | Skip — already correct |

## Stage 2: Place Pair BR-DBR

There are 3 cases. This stage reduces the remaining possibilities from 108 to 36.

Find the footprint occupied by this colored block. Ignore its orientation while choosing the case.

| Current footprint | Correction |
| --- | --- |
| `BR-DBR` | Skip — already correct |
| `FL-DFL` | `A3` |
| `FR-DFR` | `A4` |

Also correct automatically after this stage: fully solve Pair BR-DBR.

## Stage 3: Solve Pair FL-DFL

There are 2 cases. This stage reduces the remaining possibilities from 36 to 18.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `FL-DFL` | `FL/F → FL/F` | 0 (mod 1) | Skip — already correct |
| `FR-DFR` | `FL/F → FR/R` | 0 (mod 1) | `A5` |

Phase is a coordinate modulo 1 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

Also correct automatically after this stage: place Corner UBR; place Edge UR; place Corner UFL; place Edge UF; place Pair FL-DFL; place Pair FR-DFR; fully solve Pair FR-DFR.

## Stage 4: Orient Edge UR

There are 2 cases. This stage reduces the remaining possibilities from 18 to 9.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `UR` | `UR/U → UR/U` | 0 (mod 2) | Skip — already correct |
| `UR` | `UR/U → UR/R` | 1 (mod 2) | `A6` |

Phase is a coordinate modulo 2 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

Also correct automatically after this stage: fully solve Edge UF.

## Stage 5: Orient Corner UBR

There are 3 cases. This stage reduces the remaining possibilities from 9 to 3.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `UBR` | `UBR/U → UBR/U` | 0 (mod 3) | Skip — already correct |
| `UBR` | `UBR/U → UBR/B` | 1 (mod 3) | `A7` |
| `UBR` | `UBR/U → UBR/R` | 2 (mod 3) | `A8` |

Phase is a coordinate modulo 3 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

## Stage 6: Orient Corner UFL

There are 3 cases. This stage reduces the remaining possibilities from 3 to 1.

Find the footprint and the named reference sticker. The sticker cue distinguishes the observable orientations at that footprint.

| Current footprint | Reference sticker currently at | Phase | Correction |
| --- | --- | --- | --- |
| `UFL` | `UFL/U → UFL/U` | 0 (mod 3) | Skip — already correct |
| `UFL` | `UFL/U → UFL/F` | 1 (mod 3) | `A9` |
| `UFL` | `UFL/U → UFL/L` | 2 (mod 3) | `A10` |

Phase is a coordinate modulo 3 in the declared reference and destination frames. Phase 0 at the reference footprint is solved. The concrete sticker cue is the recognition rule; a phase number is not an instruction to twist this block independently.

Also correct automatically after this stage: fully solve Corner UFR.

## Shared correction algorithms

Singmaster notation uses U/R/F/D/L/B face turns, an apostrophe for the inverse, and 2 for a half turn. Execute each complete expanded word below.

Expressions retain original-loop provenance. `[A, B]` means A B A⁻¹ B⁻¹; `conj(S, A)` means S A S⁻¹. A power repeats the enclosed word. The expanded face turns are authoritative for execution.

### A1

12 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L662)^-1`

```text
U' R' U F U F' U' R U F U' F'
```

### A2

12 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L662^-1)^-1`

```text
F U F' U' R' U F U' F' U' R U
```

### A3

10 face turns (HTM), 14 quarter turns (QTM).

Expression: `(L175)^-1`

```text
F R' F R F2 R' F2 R' F2 R2
```

### A4

11 face turns (HTM), 14 quarter turns (QTM).

Expression: `L527`

```text
F R' U F2 U' F R F2 R' F2 R
```

### A5

11 face turns (HTM), 14 quarter turns (QTM).

Expression: `(L285)^-1`

```text
R' F U' R2 U R' F' R2 F R2 F'
```

### A6

10 face turns (HTM), 12 quarter turns (QTM).

Expression: `(L142)^-1`

```text
U F' U' F2 R' F' R2 U' R' U
```

### A7

19 face turns (HTM), 24 quarter turns (QTM).

Expression: `(L142)^-2`

```text
U F' U' F2 R' F' R2 U' R' U2 F' U' F2 R' F' R2 U' R' U
```

### A8

19 face turns (HTM), 24 quarter turns (QTM).

Expression: `(L142)^2`

```text
U' R U R2 F R F2 U F U2 R U R2 F R F2 U F U'
```

### A9

24 face turns (HTM), 24 quarter turns (QTM).

Expression: `(L662 L732^-1)^-1`

```text
U F U' R' U' R U F' U' R' U R U' R' U F U F' U' R U F U' F'
```

### A10

24 face turns (HTM), 24 quarter turns (QTM).

Expression: `(L662^-1)^-1 L732^-1`

```text
F U F' U' R' U F U' F' U' R U R' U' R U F U' R' U R U F' U'
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

### L527

```text
F R' U F2 U' F R F2 R' F2 R
```

After the final stage, every modeled corner and edge sticker is solved. Unmarked center spin and independent virtual-core spin are outside this model.
