use crate::Partition;

pub struct Fixture {
    pub name: &'static str,
    pub partition: Partition,
    pub shapes: usize,
    pub clockwise_arcs: usize,
    pub eccentricity_qtm: usize,
}

/// Parse the existing CSV without modifying it or adding runtime dependencies.
pub fn legacy() -> Vec<Fixture> {
    include_str!("../../../puzzles/database.csv")
        .lines()
        .skip(1)
        .zip([(1449, 2048, 16), (121, 168, 7), (1938, 2968, 20)])
        .map(|(line, (shapes, clockwise_arcs, eccentricity_qtm))| {
            let mut fields = line.split(',');
            let name = fields.next().unwrap();
            let labels: Vec<u8> = fields
                .next()
                .unwrap()
                .split('.')
                .map(|s| s.parse().unwrap())
                .collect();
            Fixture {
                name,
                partition: Partition::from_legacy(labels.try_into().unwrap()).unwrap(),
                shapes,
                clockwise_arcs,
                eccentricity_qtm,
            }
        })
        .collect()
}
