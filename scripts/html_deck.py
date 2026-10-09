#!/usr/bin/env python3
"""Package authored HTML slides as an offline, editable presentation."""
import argparse
import base64
import hashlib
from html import escape
import io
import json
from pathlib import Path
import re
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from lxml import html as html_parser

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent/'assets/approved-style'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_file(project, name):
    path = (project/name).resolve()
    if not path.is_relative_to(project) or not path.is_file():
        raise ValueError(f'Project file is missing or outside project: {name}')
    return path


def validate_fragment(body):
    root = html_parser.fragment_fromstring(body, create_parent='div')
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag.lower() in ('script', 'iframe', 'object', 'embed', 'link', 'style', 'form'):
            raise ValueError(f'Unsupported element in authored slide: {el.tag}')
        for attr, value in el.attrib.items():
            if attr.lower().startswith('on'):
                raise ValueError('Event handlers do not belong in slide fragments')
            if attr.lower() in ('src', 'href', 'xlink:href'):
                if not value.startswith(('#', 'data:image/')):
                    raise ValueError('Embed images; keep source links in notes, not active slide dependencies')
            if re.search(r'url\(\s*[\"\']?(?!data:|#)', value, re.I):
                raise ValueError('External CSS asset in slide fragment')
    return root


def build(project, font_dir=None):
    manifest_path = project/'deck.json'
    manifest = json.loads(manifest_path.read_text())
    slides = manifest.get('slides', [])
    if not isinstance(slides, list) or not slides:
        raise ValueError('deck.json requires slides')
    if font_dir is None:
        from fonts import CACHE
        font_dir = CACHE
    font_dir = Path(font_dir).resolve()
    paths = [manifest_path, Path(__file__), *[ASSETS/f for f in ('tokens.json', 'theme.css', 'viewer.js', 'shell.html')]]
    tokens = json.loads((ASSETS/'tokens.json').read_text())
    variables = ';'.join('--'+key+':'+value for key, value in tokens['colors'].items())
    variables += ';'+';'.join('--type-'+key+':'+str(value)+'px' for key,value in tokens['type_html'].items())
    variables += ';'+';'.join('--space-'+key.replace('_','-')+':'+str(value)+'px' for key,value in tokens['space_html'].items())
    css = ':root{'+variables+';--scale:1;color-scheme:light}\n'+(ASSETS/'theme.css').read_text()
    if manifest.get('css'):
        custom = local_file(project, manifest['css'])
        paths.append(custom)
        css += '\n'+custom.read_text()
    if re.search(r'@import|url\(\s*[\"\']?(?!data:|#)', css, re.I):
        raise ValueError('CSS must be self-contained')
    js = (ASSETS/'viewer.js').read_text()
    ids = set()
    sections = []
    for n, spec in enumerate(slides, 1):
        sid = spec.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', sid) or sid in ids:
            raise ValueError(f'Invalid or duplicate slide id: {sid}')
        ids.add(sid)
        path = local_file(project, spec.get('html', ''))
        paths.append(path)
        body = path.read_text()
        validate_fragment(body)
        title = escape(spec.get('title') or spec.get('claim') or sid, quote=True)
        claim = escape(spec.get('claim', ''), quote=True)
        classes = spec.get('classes', '')
        if not re.fullmatch(r'[A-Za-z0-9_\- ]*', classes):
            raise ValueError('Slide classes must be CSS class names')
        sources = spec.get('sources', [])
        if not isinstance(sources, list):
            raise ValueError('sources must be an array')
        note_text = spec.get('notes', '')+'\n'+'\n'.join(str(x) for x in sources)
        notes = ''.join('<p>'+escape(p)+'</p>' for p in note_text.splitlines() if p.strip())
        foot = '<p class="footnote editable">'+escape(spec['footnote'])+'</p>' if spec.get('footnote') else ''
        sections.append(f'<section id="slide-{sid}" class="slide {classes} {"active" if n==1 else ""}" data-title="{title}" data-claim="{claim}" aria-label="第 {n} 页：{title}" aria-hidden="{str(n!=1).lower()}">\n{body}\n{foot}<span class="folio">{n:02d}</span><template class="notes">{notes}</template></section>')
    shell = (ASSETS/'shell.html').read_text().replace('__SLIDES__', '\n'.join(sections))
    shell = shell.replace('__BRAND__', escape(manifest.get('brand', '演示文稿'))).replace('__TITLE__', escape(manifest.get('title', '演示文稿')))
    text = html_parser.fromstring(shell).text_content()+js+'上一页下一页关闭备注编辑保存复制0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    font_css = []
    for weight, style in ((400, 'Regular'), (700, 'Bold')):
        path = font_dir/f'NotoSansSC-{style}.ttf'
        paths.append(path)
        font = TTFont(path)
        missing = sorted({c for c in text if not c.isspace() and ord(c) not in font.getBestCmap()})
        if missing:
            raise ValueError(f'{style} lacks glyphs: {"".join(missing)}')
        options = subset.Options()
        options.flavor = 'woff'
        sub = subset.Subsetter(options=options)
        sub.populate(text=text)
        sub.subset(font)
        font.flavor = 'woff'
        buf = io.BytesIO()
        font.save(buf)
        font.close()
        data = base64.b64encode(buf.getvalue()).decode()
        font_css.append(f"@font-face{{font-family:'PPT Agent Sans';font-style:normal;font-weight:{weight};font-display:swap;src:url(data:font/woff;base64,{data}) format('woff')}}")
    license_path = font_dir/'OFL.txt'
    paths.append(license_path)
    license_text = license_path.read_text().replace('--', '—')
    doc = '<!doctype html>\n<!-- Embedded Noto Sans SC subset, SIL Open Font License 1.1.\n'+license_text+'\n-->\n'
    doc += '<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(manifest.get('title', '演示文稿'))+'</title><style>\n'+'\n'.join(font_css)+'\n'+css+'</style></head><body>\n'+shell+'\n<script>\n'+js+'\n</script></body></html>'
    (project/'output').mkdir(exist_ok=True)
    (project/'build/html').mkdir(parents=True, exist_ok=True)
    output = project/'output/presentation.html'
    output.write_text(doc)
    report = {'built': True, 'reviewed': False, 'pages': len(slides), 'html_sha256': sha(output), 'inputs': {str(p):sha(p) for p in paths}}
    (project/'build/html/build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'output': str(output), 'pages': len(slides), 'reviewed': False}, ensure_ascii=False))


def approve(project, note):
    report_path = project/'build/html/build.json'
    report = json.loads(report_path.read_text())
    if sha(project/'output/presentation.html') != report['html_sha256'] or any(not Path(p).is_file() or sha(p)!=s for p,s in report['inputs'].items()):
        raise ValueError('HTML or source changed; rebuild and review')
    rendered = json.loads((project/'build/html/render.json').read_text())
    if not rendered.get('ok') or rendered['html_sha256']!=report['html_sha256']:
        raise ValueError('Current HTML requires successful actual browser rendering')
    if any(not Path(p).is_file() or sha(p)!=s for p,s in rendered.get('render_hashes',{}).items()) or not rendered.get('render_hashes'):
        raise ValueError('Rendered pages changed or are missing')
    if not note.strip():
        raise ValueError('Record the concrete result of actual visual review')
    report.update(reviewed=True, review_note=note.strip())
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('Current HTML review recorded.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build_parser = sub.add_parser('build')
    build_parser.add_argument('project', type=Path)
    build_parser.add_argument('--fonts-dir', type=Path)
    approval_parser = sub.add_parser('approve')
    approval_parser.add_argument('project', type=Path)
    approval_parser.add_argument('--note', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'build': build(args.project.resolve(), args.fonts_dir)
        else: approve(args.project.resolve(), args.note)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
