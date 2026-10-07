//! Repeatable exact counts and bounded/full enumeration experiments.
use bandaged_cube_engine::enumeration::{
    CuboidFamily, EnumerationModel, ScanOptions, enumerate, sample,
};
use std::{
    fs::File,
    io::{BufWriter, Write},
    time::Instant,
};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut model = EnumerationModel::ShellCuboids;
    let mut options = ScanOptions::default();
    let mut output = None;
    let mut sample_count = None;
    let mut random_seed = 1u64;
    let mut random_seed_set = false;
    let mut core_bonds_set = false;
    let mut strict_core_set = false;
    let mut cursor = 1;
    while cursor < args.len() {
        match args[cursor].as_str() {
            "--core-bonds" => {
                core_bonds_set = true;
                model = EnumerationModel::FullCuboids;
            }
            "--strict-core-singleton" => {
                strict_core_set = true;
                model = EnumerationModel::StrictCoreSingletonCuboids;
            }
            "--implicit-bonds" => options.implicit_bonds = true,
            "--max-seeds"
            | "--max-component-vertices"
            | "--output"
            | "--samples"
            | "--random-seed" => {
                let flag = &args[cursor];
                cursor += 1;
                let value = args
                    .get(cursor)
                    .ok_or_else(|| format!("{flag} needs a value"))?;
                match flag.as_str() {
                    "--max-seeds" => options.max_seeds = Some(value.parse()?),
                    "--max-component-vertices" => {
                        options.max_component_vertices = Some(value.parse()?)
                    }
                    "--samples" => sample_count = Some(value.parse::<usize>()?),
                    "--random-seed" => {
                        random_seed = value.parse()?;
                        random_seed_set = true;
                    }
                    _ => output = Some(value.clone()),
                }
            }
            other => return Err(format!("unknown argument {other:?}").into()),
        }
        cursor += 1;
    }
    if core_bonds_set && strict_core_set {
        return Err("--core-bonds and --strict-core-singleton cannot both be enabled".into());
    }
    if options.max_seeds == Some(0) || options.max_component_vertices == Some(0) {
        return Err("limits must be positive".into());
    }
    if sample_count == Some(0) {
        return Err("sample count must be positive".into());
    }
    if args.first().map(String::as_str) != Some("sample")
        && (sample_count.is_some() || random_seed_set)
    {
        return Err("--samples and --random-seed require the sample command".into());
    }
    let family = CuboidFamily::new(model);
    let started = Instant::now();
    match args.first().map(String::as_str) {
        Some("count") => {
            if options.implicit_bonds || options.max_seeds.is_some() || options.max_component_vertices.is_some() || output.is_some() {
                return Err("count supports only --core-bonds or --strict-core-singleton".into());
            }
            let counts = family.count();
            println!("model,placements,partitions,rotation_classes,memo_states,seconds");
            println!("{},{},{},{},{},{:.6}", model.name(), counts.placements, counts.partitions,
                counts.rotation_classes, counts.memo_states, started.elapsed().as_secs_f64());
        }
        Some("generate") => {
            if options.implicit_bonds || options.max_component_vertices.is_some() || output.is_some() {
                return Err("generate supports model flags and --max-seeds".into());
            }
            let mut generator = family.partitions();
            let mut generated = 0;
            let mut checksum = 0;
            let complete = loop {
                let Some(shape) = generator.next() else { break true; };
                if options.max_seeds == Some(generated) { break false; }
                generated += 1;
                checksum ^= shape.bits().rotate_left((generated % 64) as u32);
            };
            println!("model,generated,complete,seconds,checksum");
            println!("{},{},{},{:.6},{checksum:016x}", model.name(), generated, complete, started.elapsed().as_secs_f64());
        }
        Some("scan") | Some("sample") => {
            let sampled = args[0] == "sample";
            if sampled && sample_count.is_none() {
                return Err("sample requires --samples N".into());
            }
            let mut last_report = Instant::now();
            let report = |progress: &bandaged_cube_engine::enumeration::ScanProgress| {
                if last_report.elapsed().as_secs_f64() >= 2.0 {
                    eprintln!("seeds={} classes={} components={} expanded_vertices={} rotation_keys={} largest_component={} seconds={:.3}",
                        progress.seeds_scanned, progress.classes, progress.raw_components_explored,
                        progress.expanded_shape_vertices, progress.raw_rotation_keys_seen,
                        progress.largest_component, started.elapsed().as_secs_f64());
                    last_report = Instant::now();
                }
            };
            let result = if sampled {
                sample(&family, options, sample_count.unwrap(), random_seed, report)
            } else {
                enumerate(&family, options, report)
            };
            let seconds = started.elapsed().as_secs_f64();
            let p = &result.progress;
            println!("model,implicit_bonds,seeds_scanned,raw_components,expanded_vertices,raw_rotation_keys,closed_rotation_keys,classes,largest_component,complete,stop_reason,seconds");
            println!("{},{},{},{},{},{},{},{},{},{},{},{:.6}", model.name(), options.implicit_bonds,
                p.seeds_scanned,p.raw_components_explored,p.expanded_shape_vertices,p.raw_rotation_keys_seen,
                p.closed_rotation_keys_seen,p.classes,p.largest_component,result.complete,result.stop_reason.unwrap_or(""),seconds);
            if let Some(path) = output {
                let mut writer = BufWriter::new(File::create(path)?);
                writeln!(writer, "# bandaged-cube-enumeration-v1 model={} core_bonds={} symmetry=proper-rotations motion=outer-face-turns implicit_bonds={} complete={} stop_reason={} seeds_scanned={} seconds={:.6} mode={} random_seed={} samples={}",
                    model.name(), model == EnumerationModel::FullCuboids, options.implicit_bonds,
                    result.complete, result.stop_reason.unwrap_or(""), p.seeds_scanned, seconds,
                    args[0], random_seed, sample_count.unwrap_or(0))?;
                writeln!(writer, "representative_axis_major,raw_component_vertices,representative_labels,seed_labels")?;
                for class in result.representatives {
                    let labels = |values: &[u8;27]| values.iter().map(u8::to_string).collect::<Vec<_>>().join(" ");
                    writeln!(writer, "{:014x},{},{},{}", class.representative.bits(),class.raw_component_vertices,
                        labels(class.representative.to_partition().labels()),labels(class.seed.to_partition().labels()))?;
                }
                writer.flush()?;
            }
        }
        _ => return Err("usage: enumerate count|generate|scan|sample [--core-bonds|--strict-core-singleton] [--implicit-bonds] [--max-seeds N] [--max-component-vertices N] [--output PATH] [--samples N --random-seed SEED]".into()),
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
