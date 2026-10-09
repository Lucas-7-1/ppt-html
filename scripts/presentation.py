#!/usr/bin/env python3
"""Build requested presentation formats; an omitted format means native PPTX."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def formats(manifest):
    values = manifest.get('deliverables', ['pptx'])
    if not isinstance(values, list) or not values or any(x not in ('pptx', 'html') for x in values):
        raise ValueError('deliverables must contain pptx and/or html')
    return list(dict.fromkeys(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'route'])
    parser.add_argument('project', type=Path)
    parser.add_argument('--fonts-dir', type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    selected = formats(json.loads((project/'deck.json').read_text()))
    print(json.dumps({'deliverables': selected}, ensure_ascii=False), flush=True)
    if args.command == 'route': return
    for target in selected:
        script = HERE/('deck.py' if target=='pptx' else 'html_deck.py')
        cmd = [sys.executable, str(script), 'build', str(project)]
        if target=='html' and args.fonts_dir: cmd += ['--fonts-dir', str(args.fonts_dir)]
        subprocess.run(cmd, check=True)


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
