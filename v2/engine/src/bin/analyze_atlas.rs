//! Postprocess a complete, implicitly closed shell atlas without regenerating seeds.
use bandaged_cube_engine::{
    BondShape, Face, Partition,
    explore::explore,
    symmetry::{canonical_key, reflect},
};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{BufWriter, Write},
    time::Instant,
};

#[derive(Clone, Copy)]
enum DeadEnds {
    None,
    Frozen,
    OneAxis,
    UnchangingShape,
}

impl DeadEnds {
    fn name(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Frozen => "frozen",
            Self::OneAxis => "one-axis",
            Self::UnchangingShape => "unchanging-shape",
        }
    }

    fn retains(self, value: &Measurement) -> bool {
        match self {
            Self::None => true,
            Self::Frozen => value.ever_faces != 0,
            Self::OneAxis => value.axis_count() >= 2,
            Self::UnchangingShape => value.vertices > 1,
        }
    }
}

struct AtlasRow {
    key: u64,
    shape: BondShape,
    csv: String,
}

struct Measurement {
    key: u64,
    mirror: u64,
    vertices: usize,
    rotation_keys: usize,
    ever_faces: u8,
}

impl Measurement {
    fn axis_count(&self) -> u32 {
        let mut axes = 0u8;
        for face in Face::ALL {
            if self.ever_faces & (1 << face.index()) != 0 {
                let normal = face.normal();
                let axis = normal.iter().position(|&value| value != 0).unwrap();
                axes |= 1 << axis;
            }
        }
        axes.count_ones()
    }
}

fn read_atlas(path: &str) -> Result<(String, Vec<AtlasRow>), Box<dyn std::error::Error>> {
    let data = fs::read_to_string(path)?;
    let mut lines = data.lines();
    let metadata = lines.next().ok_or("empty atlas")?;
    let attributes: HashMap<_, _> = metadata
        .split_whitespace()
        .filter_map(|token| token.split_once('='))
        .collect();
    for (key, expected) in [
        ("model", "shell-cuboids"),
        ("core_bonds", "false"),
        ("symmetry", "proper-rotations"),
        ("implicit_bonds", "true"),
        ("complete", "true"),
        ("motion", "outer-face-turns"),
    ] {
        if attributes.get(key) != Some(&expected) {
            return Err(format!("atlas requires {key}={expected}").into());
        }
    }
    let header = lines.next().ok_or("missing CSV header")?.to_owned();
    if header
        != "representative_axis_major,raw_component_vertices,representative_labels,seed_labels"
    {
        return Err("unsupported atlas columns".into());
    }
    let mut rows = Vec::new();
    let mut unique = HashSet::new();
    for line in lines {
        let fields: Vec<_> = line.split(',').collect();
        if fields.len() != 4 {
            return Err("invalid atlas row".into());
        }
        let key = u64::from_str_radix(fields[0], 16)?;
        let labels = fields[2]
            .split_whitespace()
            .map(str::parse::<u8>)
            .collect::<Result<Vec<_>, _>>()?;
        let labels: [u8; 27] = labels.try_into().map_err(|_| "expected 27 labels")?;
        let partition = Partition::from_legacy(labels)?;
        if *partition.labels() != labels
            || labels.iter().filter(|&&label| label == labels[13]).count() != 1
        {
            return Err("atlas labels must be normalized with an independent core".into());
        }
        let shape = BondShape::from_partition(&partition);
        if canonical_key(shape) != key || !unique.insert(key) {
            return Err("invalid or duplicate class identifier".into());
        }
        rows.push(AtlasRow {
            key,
            shape,
            csv: line.to_owned(),
        });
    }
    Ok((header, rows))
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let input = args.first().ok_or("usage: analyze_atlas INPUT.csv [--dead-ends none|frozen|one-axis|unchanging-shape] [--output OUTPUT.csv] [--summary SUMMARY.json] [--pairs PAIRS.csv]")?;
    let mut policy = DeadEnds::OneAxis;
    let mut output = None;
    let mut summary_path = None;
    let mut pairs_path = None;
    let mut cursor = 1;
    while cursor < args.len() {
        let flag = &args[cursor];
        cursor += 1;
        let value = args
            .get(cursor)
            .ok_or_else(|| format!("{flag} requires a value"))?;
        match flag.as_str() {
            "--dead-ends" => {
                policy = match value.as_str() {
                    "none" => DeadEnds::None,
                    "frozen" => DeadEnds::Frozen,
                    "one-axis" => DeadEnds::OneAxis,
                    "unchanging-shape" => DeadEnds::UnchangingShape,
                    _ => return Err(format!("unknown dead-end policy {value:?}").into()),
                }
            }
            "--output" => output = Some(value),
            "--summary" => summary_path = Some(value),
            "--pairs" => pairs_path = Some(value),
            _ => return Err(format!("unknown argument {flag:?}").into()),
        }
        cursor += 1;
    }
    if [output, summary_path, pairs_path]
        .into_iter()
        .flatten()
        .any(|path| path == input)
    {
        return Err("output paths must differ from the source atlas".into());
    }
    let started = Instant::now();
    let (header, rows) = read_atlas(input)?;
    let mut measurements = Vec::new();
    let mut expanded = 0;
    let mut last_report = Instant::now();
    for row in &rows {
        let graph = explore(row.shape);
        assert!(graph.complete);
        let mut keys = HashSet::new();
        let mut mirror = u64::MAX;
        for &shape in &graph.vertices {
            keys.insert(canonical_key(shape));
            mirror = mirror.min(canonical_key(reflect(shape)));
        }
        assert_eq!(
            keys.iter().copied().min(),
            Some(row.key),
            "representative must minimize its entire component"
        );
        let ever_faces = graph.arcs.iter().fold(0, |mask, &(_, _, movement)| {
            mask | (1 << movement.face.index())
        });
        expanded += graph.vertices.len();
        measurements.push(Measurement {
            key: row.key,
            mirror,
            vertices: graph.vertices.len(),
            rotation_keys: keys.len(),
            ever_faces,
        });
        if last_report.elapsed().as_secs_f64() >= 2.0 {
            eprintln!(
                "classes={}/{} vertices={} seconds={:.3}",
                measurements.len(),
                rows.len(),
                expanded,
                started.elapsed().as_secs_f64()
            );
            last_report = Instant::now();
        }
    }
    let by_key: HashMap<_, _> = measurements
        .iter()
        .map(|value| (value.key, value))
        .collect();
    for value in &measurements {
        let partner = by_key
            .get(&value.mirror)
            .ok_or("mirror class is missing from the atlas")?;
        assert_eq!(
            partner.mirror, value.key,
            "mirror matching must be involutive"
        );
        assert_eq!(partner.vertices, value.vertices);
        assert_eq!(partner.rotation_keys, value.rotation_keys);
        assert_eq!(
            partner.ever_faces.count_ones(),
            value.ever_faces.count_ones()
        );
        assert_eq!(partner.axis_count(), value.axis_count());
    }
    let achiral = measurements
        .iter()
        .filter(|value| value.key == value.mirror)
        .count();
    let chiral_pairs = (rows.len() - achiral) / 2;
    assert_eq!(achiral + 2 * chiral_pairs, rows.len());
    let counts = |filter: DeadEnds| {
        let proper = measurements
            .iter()
            .filter(|value| filter.retains(value))
            .count();
        let mirrors: HashSet<_> = measurements
            .iter()
            .filter(|value| filter.retains(value))
            .map(|value| value.key.min(value.mirror))
            .collect();
        (proper, mirrors.len())
    };
    let (proper_none, mirror_none) = counts(DeadEnds::None);
    let (proper_frozen, mirror_frozen) = counts(DeadEnds::Frozen);
    let (proper_axis, mirror_axis) = counts(DeadEnds::OneAxis);
    let (proper_shape, mirror_shape) = counts(DeadEnds::UnchangingShape);
    let selected = counts(policy).1;
    let seconds = started.elapsed().as_secs_f64();
    let summary = format!(
        concat!(
            "{{\n  \"schema\": \"bandaged-cube-atlas-analysis-v1\",\n",
            "  \"model\": \"shell-cuboids\",\n  \"core_bonds\": false,\n  \"implicit_bonds\": true,\n",
            "  \"complete\": true,\n  \"source_classes\": {},\n  \"achiral_classes\": {},\n  \"chiral_pairs\": {},\n",
            "  \"expanded_closed_vertices\": {},\n  \"dead_end_filter\": \"{}\",\n  \"filtered_mirror_classes\": {},\n",
            "  \"counts\": {{\n",
            "    \"none\": {{\"proper_rotations\": {}, \"rotations_and_reflections\": {}}},\n",
            "    \"frozen\": {{\"proper_rotations\": {}, \"rotations_and_reflections\": {}}},\n",
            "    \"one-axis\": {{\"proper_rotations\": {}, \"rotations_and_reflections\": {}}},\n",
            "    \"unchanging-shape\": {{\"proper_rotations\": {}, \"rotations_and_reflections\": {}}}\n",
            "  }},\n  \"seconds\": {:.6}\n}}\n"
        ),
        rows.len(),
        achiral,
        chiral_pairs,
        expanded,
        policy.name(),
        selected,
        proper_none,
        mirror_none,
        proper_frozen,
        mirror_frozen,
        proper_axis,
        mirror_axis,
        proper_shape,
        mirror_shape,
        seconds
    );
    print!("{summary}");
    if let Some(path) = summary_path {
        fs::write(path, &summary)?;
    }
    if let Some(path) = pairs_path {
        let mut writer = BufWriter::new(fs::File::create(path)?);
        writeln!(
            writer,
            "class_id,mirror_class_id,fixed_frame_vertices,proper_rotation_shape_keys,ever_faces,ever_axes"
        )?;
        for value in &measurements {
            let faces = Face::ALL
                .into_iter()
                .filter(|face| value.ever_faces & (1 << face.index()) != 0)
                .map(|face| face.to_string())
                .collect::<Vec<_>>()
                .join(" ");
            writeln!(
                writer,
                "{:014x},{:014x},{},{},{},{}",
                value.key,
                value.mirror,
                value.vertices,
                value.rotation_keys,
                faces,
                value.axis_count()
            )?;
        }
        writer.flush()?;
    }
    if let Some(path) = output {
        let mut writer = BufWriter::new(fs::File::create(path)?);
        writeln!(
            writer,
            "# bandaged-cube-enumeration-v1 model=shell-cuboids core_bonds=false symmetry=rotations-and-reflections motion=outer-face-turns implicit_bonds=true complete=true dead_end_filter={} source_classes={} classes={}",
            policy.name(),
            rows.len(),
            selected
        )?;
        writeln!(writer, "{header}")?;
        let mut written = 0;
        for row in &rows {
            let value = by_key[&row.key];
            if policy.retains(value) && value.key <= value.mirror {
                writeln!(writer, "{}", row.csv)?;
                written += 1;
            }
        }
        assert_eq!(written, selected);
        writer.flush()?;
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
