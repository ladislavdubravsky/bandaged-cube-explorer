#[allow(dead_code)]
#[path = "src/geometry.rs"]
mod geometry;

use geometry::{BONDS, CORNER_CELLS, CORNER_FACES, EDGE_CELLS, EDGE_FACES, Face, Move};
use std::{collections::BTreeMap, env, fmt::Write, fs, path::PathBuf};

// Original 48 shell positions, extended into free slots for six core bonds.
// Source: ladislavdubravsky/bandaged-cubes-enumerator, commit 7bd0e68.
const LEGACY: [u8; 54] = [
    17, 50, 56, 24, 9, 1, 10, 11, 63, 34, 30, 35, 8, 12, 5, 33, 29, 28, 46, 4, 21, 25, 0, 42, 16,
    13, 3, 32, 15, 7, 41, 47, 14, 22, 39, 49, 23, 44, 6, 2, 48, 19, 60, 40, 27, 31, 38, 20, 26, 45,
    43, 51, 37, 18,
];

fn bond_destination(bond: usize, movement: Move) -> usize {
    let [a, b] = BONDS[bond];
    if movement.face.contains(a) && movement.face.contains(b) {
        geometry::bond_index(
            geometry::destination(a, movement),
            geometry::destination(b, movement),
        )
    } else {
        bond
    } // Boundary bits are zero for a legal turn.
}

fn layout(output: &mut String, name: &str, positions: [u8; 54]) {
    let mut used = 0u64;
    for bit in positions {
        assert!(bit < 64 && used & (1 << bit) == 0);
        used |= 1 << bit;
    }
    let mut blockers = [0u64; 6];
    for face in Face::ALL {
        for (i, [a, b]) in BONDS.into_iter().enumerate() {
            if face.contains(a) != face.contains(b) {
                blockers[face.index()] |= 1 << positions[i];
            }
        }
    }
    let mut expressions = Vec::new();
    let mut counts = [0usize; 18];
    let mut moving = [0u64; 6];
    let mut destinations = [[0u8; 54]; 18];
    for movement in Move::ALL {
        let mut groups = BTreeMap::<i8, u64>::new();
        for (i, bit) in positions.into_iter().enumerate() {
            let to = bond_destination(i, movement);
            destinations[movement.index()][i] = positions[to];
            *groups.entry(positions[to] as i8 - bit as i8).or_default() |= 1 << bit;
            let [a, b] = BONDS[i];
            if movement.face.contains(a) && movement.face.contains(b) {
                moving[movement.face.index()] |= 1 << bit;
            }
        }
        counts[movement.index()] = groups.keys().filter(|&&shift| shift != 0).count();
        expressions.push(
            groups
                .into_iter()
                .map(|(shift, mask)| {
                    let masked = format!("(bits & {mask:#018x}u64)");
                    if shift < 0 {
                        format!("({masked} >> {})", -shift)
                    } else if shift > 0 {
                        format!("({masked} << {shift})")
                    } else {
                        masked
                    }
                })
                .collect::<Vec<_>>()
                .join(" | "),
        );
    }
    writeln!(
        output,
        "#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)] pub struct {name};"
    )
    .unwrap();
    writeln!(output, "impl sealed::Sealed for {name} {{}}").unwrap();
    writeln!(output, "impl BondLayout for {name} {{").unwrap();
    writeln!(output, "const NAME: &'static str = \"{name}\";").unwrap();
    writeln!(output, "const POSITIONS: [u8; 54] = {positions:?};").unwrap();
    writeln!(output, "const USED_MASK: u64 = {used:#018x};").unwrap();
    writeln!(output, "const BLOCKERS: [u64; 6] = {blockers:?};").unwrap();
    writeln!(output, "const MOVING: [u64; 6] = {moving:?};").unwrap();
    writeln!(
        output,
        "const DESTINATIONS: [[u8; 54]; 18] = {destinations:?};"
    )
    .unwrap();
    writeln!(output, "const SHIFT_GROUPS: [usize; 18] = {counts:?};").unwrap();
    writeln!(
        output,
        "#[inline] fn permute(bits: u64, movement: Move) -> u64 {{ match movement.index() {{"
    )
    .unwrap();
    for (i, expression) in expressions.into_iter().enumerate() {
        writeln!(output, "{i} => {expression},").unwrap();
    }
    writeln!(output, "_ => unreachable!(), }} }} }}").unwrap();
}

fn colored(output: &mut String) {
    let mut corner_dest = [[0u8; 8]; 18];
    let mut corner_delta = [[0u8; 8]; 18];
    let mut edge_dest = [[0u8; 12]; 18];
    let mut edge_delta = [[0u8; 12]; 18];
    for movement in Move::ALL {
        for (source, cell) in CORNER_CELLS.into_iter().enumerate() {
            let dest_cell = geometry::destination(cell, movement);
            let dest = CORNER_CELLS.iter().position(|&c| c == dest_cell).unwrap();
            corner_dest[movement.index()][source] = dest as u8;
            let mut normal = CORNER_FACES[source][0].normal();
            if movement.face.contains(cell) {
                for _ in 0..movement.amount as u8 {
                    normal = geometry::rotate_vector(normal, movement.face);
                }
            }
            corner_delta[movement.index()][source] = CORNER_FACES[dest]
                .iter()
                .position(|f| f.normal() == normal)
                .unwrap() as u8;
        }
        for (source, cell) in EDGE_CELLS.into_iter().enumerate() {
            let dest_cell = geometry::destination(cell, movement);
            let dest = EDGE_CELLS.iter().position(|&c| c == dest_cell).unwrap();
            edge_dest[movement.index()][source] = dest as u8;
            let mut normal = EDGE_FACES[source][0].normal();
            if movement.face.contains(cell) {
                for _ in 0..movement.amount as u8 {
                    normal = geometry::rotate_vector(normal, movement.face);
                }
            }
            edge_delta[movement.index()][source] = EDGE_FACES[dest]
                .iter()
                .position(|f| f.normal() == normal)
                .unwrap() as u8;
        }
    }
    writeln!(
        output,
        "const CORNER_DEST: [[u8; 8]; 18] = {corner_dest:?};"
    )
    .unwrap();
    writeln!(
        output,
        "const CORNER_DELTA: [[u8; 8]; 18] = {corner_delta:?};"
    )
    .unwrap();
    writeln!(output, "const EDGE_DEST: [[u8; 12]; 18] = {edge_dest:?};").unwrap();
    writeln!(output, "const EDGE_DELTA: [[u8; 12]; 18] = {edge_delta:?};").unwrap();
}

fn main() {
    println!("cargo:rerun-if-changed=src/geometry.rs");
    println!("cargo:rerun-if-changed=layouts/tuned.txt");
    let natural = std::array::from_fn(|i| i as u8);
    let tuned: Vec<u8> = fs::read_to_string("layouts/tuned.txt")
        .unwrap()
        .split_whitespace()
        .map(|s| s.parse().unwrap())
        .collect();
    let mut output = String::from("// Generated from coordinates. Do not edit.\n");
    layout(&mut output, "AxisMajor", natural);
    layout(&mut output, "LegacySparse", LEGACY);
    layout(
        &mut output,
        "Tuned",
        tuned
            .try_into()
            .expect("tuned layout must contain 54 bit positions"),
    );
    let root = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    fs::write(root.join("bond_tables.rs"), output).unwrap();
    let mut output = String::from("// Generated cubie destination and orientation tables.\n");
    colored(&mut output);
    fs::write(root.join("colored_tables.rs"), output).unwrap();
}
