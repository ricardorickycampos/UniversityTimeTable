"""
    python main.py phase1 --config scripts/config.yaml
    python main.py phase2 --config scripts/config.yaml --genome results/run_best.npy
    python main.py all --config scripts/config.yaml
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json
from src.scheduling.main import run_phase1
from src.sectioning.main import run_phase2

def run_complete_pipeline(config_path: str | Path):
    # Run both Phase 1 and Phase 2 sequentially.
    config_path = Path(config_path)
    print(f"--- Starting Phase 1 (Schedule Building) ---")
    p1_log = run_phase1(config_path)
    
    with open(p1_log) as f:
        log_data = json.load(f)
    genome_path = Path(log_data['genome_path'])
    
    print(f"\n--- Starting Phase 2 (Student Sectioning) ---")
    p2_log = run_phase2(config_path, genome_path)
    
    return p1_log, p2_log

def main():
    parser = argparse.ArgumentParser(description='Uni Time Tabling GA Runner')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Phase 1 commands
    p1_parser = subparsers.add_parser('phase1', help='Run Phase 1 (Schedule Building)')
    p1_parser.add_argument('--config', type=Path, default=Path('scripts/config.yaml'), help='Path to config file')

    # Phase 2 commands
    p2_parser = subparsers.add_parser('phase2', help='Run Phase 2 (Student Sectioning)')
    p2_parser.add_argument('--config', type=Path, default=Path('scripts/config.yaml'), help='Path to config file')
    p2_parser.add_argument('--genome', type=Path, default=None, help='Path to Phase 1 best genome (.npy)')

    # Both commands
    all_parser = subparsers.add_parser('all', help='Run both Phase 1 and Phase 2')
    all_parser.add_argument('--config', type=Path, default=Path('scripts/config.yaml'), help='Path to config file')

    args = parser.parse_args()

    if args.command == 'phase1':
        run_phase1(args.config)
    elif args.command == 'phase2':
        run_phase2(args.config, args.genome)
    elif args.command == 'all':
        run_complete_pipeline(args.config)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
