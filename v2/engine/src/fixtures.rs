use crate::Partition;

pub struct Fixture {
    pub name: &'static str,
    pub partition: Partition,
    pub shapes: usize,
    pub clockwise_arcs: usize,
    pub eccentricity_qtm: usize,
}

/// Parse a frozen snapshot of the legacy CSV, bundled with the engine crate.
/// The original database remains unchanged and no runtime file access is needed.
pub fn legacy() -> Vec<Fixture> {
    include_str!("../data/fixtures.csv")
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
