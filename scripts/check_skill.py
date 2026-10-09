#!/usr/bin/env python3
"""Check resource links, metadata and script syntax without building a deck."""
from pathlib import Path
import json
import re
import sys
from urllib.parse import unquote
import yaml
ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ['SKILL.md','agents/openai.yaml','references/design.md','references/principles.md',
    'references/vector-contract.md','references/project.md','references/runtime.md',
    'scripts/deck.py','scripts/svg_native.py','scripts/fonts.py','scripts/doctor.py',
    'scripts/container.mjs','scripts/runtime.mjs','scripts/preview.mjs','scripts/svg_validator.py',
    'scripts/pptx_validator.py','package.json','requirements.txt',
    'references/approved-style.md','references/html-delivery.md',
    'scripts/presentation.py','scripts/html_deck.py','scripts/render_html.mjs',
    'assets/approved-style/tokens.json','assets/approved-style/theme.css',
    'assets/approved-style/viewer.js','assets/approved-style/shell.html',
    'assets/approved-style/reference.png','assets/approved-style/reference/deck.json']

def main():
    errors = []
    for file in REQUIRED:
        path = ROOT/file
        if not path.is_file() or not path.stat().st_size: errors.append('missing or empty: '+file)
    skill = (ROOT/'SKILL.md').read_text()
    front = re.match(r'^---\n(.*?)\n---',skill,re.S)
    metadata = yaml.safe_load(front[1]) if front else {}
    if metadata.get('name') != 'ppt-agent-v7' or not metadata.get('description'): errors.append('invalid frontmatter')
    agent = yaml.safe_load((ROOT/'agents/openai.yaml').read_text())
    if '$ppt-agent-v7' not in agent.get('interface',{}).get('default_prompt',''): errors.append('agent prompt name mismatch')
    for file in [ROOT/'SKILL.md', *(ROOT/'references').glob('*.md')]:
        for target in re.findall(r'\]\(([^)]+)\)',file.read_text()):
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target): continue
            path = unquote(target.split('#',1)[0])
            if path and not (file.parent/path).exists(): errors.append(f'unresolved reference in {file.name}: {target}')
    for file in (ROOT/'scripts').glob('*.py'):
        try: compile(file.read_text(),str(file),'exec')
        except SyntaxError as error: errors.append(str(error))
    package = json.loads((ROOT/'package.json').read_text())
    if package.get('version') != '7.3.0': errors.append('package version mismatch')
    print('\n'.join(errors) if errors else 'PPT Agent v7: metadata, resources and Python syntax valid.')
    return bool(errors)
if __name__ == '__main__': sys.exit(main())
