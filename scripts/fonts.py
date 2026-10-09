#!/usr/bin/env python3
"""Resolve real fonts, check glyph coverage, and cache licensed CJK fonts."""
import argparse
import functools
import json
import os
from pathlib import Path
import subprocess
import urllib.request

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import ImageFont

CACHE = Path(os.environ.get('PPT_AGENT_FONT_DIR', str(Path.home()/'.cache/ppt-agent/fonts')))
URL = 'https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/'

def ensure(source=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    variable = CACHE/'NotoSansSC-variable.ttf'
    license_path = CACHE/'OFL.txt'
    if not variable.exists():
        if source:
            import shutil
            shutil.copyfile(source, variable)
        else:
            with urllib.request.urlopen(URL+'NotoSansSC%5Bwght%5D.ttf', timeout=60) as r:
                data=r.read()
            temp=variable.with_suffix('.download')
            temp.write_bytes(data)
            temp.replace(variable)
    if not license_path.exists():
        if source and (Path(source).parent/'OFL.txt').exists():
            license_path.write_bytes((Path(source).parent/'OFL.txt').read_bytes())
        else:
            with urllib.request.urlopen(URL+'OFL.txt', timeout=30) as r:
                license_path.write_bytes(r.read())
    for weight, style in [(400,'Regular'),(700,'Bold')]:
        target=CACHE/f'NotoSansSC-{style}.ttf'
        if not target.exists():
            font=TTFont(variable)
            static=instantiateVariableFont(font, {'wght':weight}, inplace=True)
            # Give static instances unambiguous family/style names for fontconfig.
            for name in static['name'].names:
                values={1:'Noto Sans SC',2:style,4:f'Noto Sans SC {style}',
                        6:f'NotoSansSC-{style}',16:'Noto Sans SC',17:style}
                if name.nameID in values:
                    name.string=values[name.nameID].encode(name.getEncoding(), errors='replace')
            static.save(target)
            font.close()
    # Only install fontconfig pointers for this user's cache, never alter system fonts.
    config_dir=Path.home()/'.config/fontconfig/conf.d'
    config_dir.mkdir(parents=True,exist_ok=True)
    from xml.sax.saxutils import escape
    (config_dir/'99-ppt-agent.conf').write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
        f'<fontconfig><dir>{escape(str(CACHE))}</dir>'
        '<selectfont><rejectfont><glob>*NotoSansSC-variable.ttf</glob></rejectfont></selectfont></fontconfig>')
    subprocess.run(['fc-cache','-f',str(CACHE)],check=True,capture_output=True)
    resolve.cache_clear()
    return {'family':'Noto Sans SC','fonts':[str(CACHE/'NotoSansSC-Regular.ttf'),str(CACHE/'NotoSansSC-Bold.ttf')],
            'license':str(license_path)}

@functools.lru_cache(maxsize=64)
def resolve(family, bold=False):
    family=family.split(',')[0].strip(' \"\'')
    if family=='Noto Sans SC' and (CACHE/f'NotoSansSC-{"Bold" if bold else "Regular"}.ttf').exists():
        return CACHE/f'NotoSansSC-{"Bold" if bold else "Regular"}.ttf'
    r=subprocess.run(['fc-match','-f','%{family}\n%{file}',family+(':style=Bold' if bold else '')],
                     check=True,capture_output=True,text=True)
    lines=r.stdout.splitlines()
    if len(lines)<2 or family.casefold() not in [f.strip().casefold() for f in lines[0].split(',')]:
        raise ValueError(f'font is not installed: {family!r}; run fonts.py --ensure for Noto Sans SC')
    return Path(lines[1])

@functools.lru_cache(maxsize=64)
def metrics(path):
    f=TTFont(str(path),lazy=True)
    result=(set(f.getBestCmap()), f['hhea'].ascent/f['head'].unitsPerEm,
            -f['hhea'].descent/f['head'].unitsPerEm)
    f.close()
    return result

def text_metrics(text, family, size, bold=False):
    path=resolve(family,bold)
    chars,ascent,descent=metrics(str(path))
    missing=sorted({c for c in text if not c.isspace() and ord(c) not in chars})
    if missing:
        raise ValueError(f'{family} lacks glyphs: {"".join(missing)}')
    f=ImageFont.truetype(str(path), max(1,round(size*4)))
    width=f.getlength(text)/4
    return width, size*ascent, size*descent

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ensure',action='store_true')
    parser.add_argument('--source',help='Reuse a downloaded official variable font')
    args=parser.parse_args()
    print(json.dumps(ensure(args.source) if args.ensure else {'font':str(resolve('Noto Sans SC'))},ensure_ascii=False))
