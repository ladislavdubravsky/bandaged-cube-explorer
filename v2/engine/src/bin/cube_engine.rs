use bandaged_cube_engine::{BandageSpec, BondShape, Face, explore::explore, fixtures, parse_moves};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("fixtures") if args.len() == 1 => {
            for fixture in fixtures::legacy() {
                let initial: BondShape = BondShape::from_partition(&fixture.partition);
                let graph = explore(initial, 100_000);
                let max = graph.qtm_distances(0).into_iter().flatten().max().unwrap();
                println!(
                    "{}: {} shapes, {} clockwise arcs, solved eccentricity {} QTM, complete={}",
                    fixture.name,
                    graph.vertices.len(),
                    graph.arcs.len(),
                    max,
                    graph.complete
                );
            }
        }
        Some("replay") if args.len() >= 2 => {
            let fixture = fixtures::legacy()
                .into_iter()
                .find(|f| f.name.eq_ignore_ascii_case(&args[1]))
                .ok_or_else(|| format!("unknown puzzle {:?}", args[1]))?;
            let spec = BandageSpec::new(fixture.partition);
            let mut state = spec.solved_state();
            for movement in parse_moves(&args[2..].join(" "))? {
                state.try_turn(movement)?;
            }
            println!("shape: {:?}", state.shape().to_partition().labels());
            println!("colored state: {:?}", state.cube());
            println!(
                "turnable: {}",
                Face::ALL
                    .into_iter()
                    .filter(|&face| state.is_turnable(face))
                    .map(|f| f.to_string())
                    .collect::<Vec<_>>()
                    .join(" ")
            );
        }
        _ => {
            return Err(
                "usage: cube_engine fixtures | cube_engine replay 'Alcatraz' 'F R2'".into(),
            );
        }
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
