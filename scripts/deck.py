#!/usr/bin/env python3
"""Incremental, all-vector SVG -> native PPTX build, preview and revision."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from lxml import etree
from PIL import Image, ImageDraw
from svg_native import SvgConverter, NS, normalize, local_name, px
from fonts import resolve, CACHE
from pptx_validator import validate_pptx

HERE=Path(__file__).resolve().parent

def digest(data):
    if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False,sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def run(args):
    r=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=240)
    if r.returncode:raise RuntimeError(f'{Path(args[0]).name} failed: {r.stderr[-2500:] or r.stdout[-2500:]}')
    return r.stdout

def node():
    return os.environ.get('CODEX_PRIMARY_RUNTIME_NODE') or os.environ.get('RUNTIME_NODE') or shutil.which('node') or 'node'

def binary(name):
    runtime=os.environ.get('CODEX_PRIMARY_RUNTIME_ROOT')
    if runtime:
        target=Path(runtime)/'dependencies/bin/override'/name
        if target.is_file():return str(target)
    found=shutil.which(name)
    if not found:raise RuntimeError(f'required program not available: {name}')
    return found

def load(project):
    manifest=json.loads((project/'deck.json').read_text())
    slides=manifest.get('slides')
    if not isinstance(slides,list) or not slides:raise ValueError('deck.json requires a non-empty slides array')
    ids=[]
    for slide in slides:
        sid=slide.get('id','')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',sid):raise ValueError(f'invalid slide id: {sid!r}')
        if sid in ids:raise ValueError(f'duplicate slide id: {sid}')
        ids.append(sid)
        file=(project/slide.get('svg','')).resolve()
        if not file.is_relative_to(project) or file.suffix!='.svg' or not file.is_file():
            raise ValueError(f'{sid}: SVG must exist inside this project')
        if not isinstance(slide.get('sources',[]),list):raise ValueError(f'{sid}: sources must be an array')
    for slide in slides:
        for dep in slide.get('depends_on',[]):
            if dep not in ids:raise ValueError(f'unknown dependency: {dep}')
    return manifest

def context(project,manifest):
    fonts={};raw={}
    for slide in manifest['slides']:
        source=project/slide['svg'];raw[slide['id']]=digest(source.read_bytes())
        parser=etree.XMLParser(resolve_entities=False,no_network=True)
        root=normalize(etree.parse(str(source),parser).getroot())
        for el in root.iter():
            if local_name(el.tag) not in ('text','tspan'):continue
            family=el.get('font-family','Noto Sans SC').split(',')[0].strip(' \"\'')
            bold=el.get('font-weight') in ('bold','600','700','800','900')
            font=resolve(family,bold);fonts[str(font)]=digest(font.read_bytes())
    tool_hash=digest({p.name:digest(p.read_bytes()) for p in sorted(HERE.iterdir()) if p.suffix in ('.py','.mjs')})
    runtime=json.loads(run([node(),HERE/'container.mjs','--probe']))
    shared=digest({'manifest':{k:v for k,v in manifest.items() if k!='slides'},'fonts':fonts,'compiler':tool_hash,'runtime':runtime})
    by_id={s['id']:s for s in manifest['slides']};keys={}
    def key(sid,stack=()):
        if sid in stack:raise ValueError('dependency cycle: '+' -> '.join((*stack,sid)))
        if sid not in keys:
            s=by_id[sid]
            keys[sid]=digest({'svg':raw[sid],'shared':shared,'spec':s,
                             'dependencies':[key(d,(*stack,sid)) for d in s.get('depends_on',[])]})
        return keys[sid]
    for sid in by_id:key(sid)
    return keys,fonts,digest({'manifest':manifest,'keys':keys})

def source_texts(source):
    parser=etree.XMLParser(resolve_entities=False,no_network=True)
    root=etree.parse(str(source),parser).getroot();texts=[]
    def walk(el,stack=()):
        tag=local_name(el.tag)
        if el.get('display')=='none' or el.get('visibility')=='hidden' or float(el.get('opacity',1))<=0:return
        if tag in ('defs','title','desc','metadata'):return
        if tag=='use':
            href=el.get('href') or el.get('{http://www.w3.org/1999/xlink}href','')
            if href in stack:raise ValueError('recursive use')
            matches=root.xpath('//*[@id=$id]',id=href.lstrip('#'))
            if len(matches)!=1:raise ValueError('invalid use reference')
            walk(matches[0],(*stack,href));return
        if tag=='text':
            spans=[c for c in el if local_name(c.tag)=='tspan']
            for c in spans or [el]:
                text=''.join(c.itertext())
                if text.strip():texts.append(text)
            return
        for child in el:walk(child,stack)
    walk(root);return texts

def verify_content(pptx,manifest,project):
    with zipfile.ZipFile(pptx) as z:
        for i,s in enumerate(manifest['slides'],1):
            root=etree.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
            actual=[el.text or '' for el in root.findall('.//a:t',NS)]
            expected=source_texts(project/s['svg'])
            if actual!=expected:raise ValueError(f'{s["id"]}: exported text differs from SVG source')
            names=[el.get('name') for el in root.findall('.//p:cNvPr',NS)]
            if len(names)!=len(set(names)):raise ValueError(f'{s["id"]}: duplicate object names')
            if root.findall('.//p:pic',NS):raise ValueError('picture found in all-vector PPTX')
            for shape in root.findall('.//p:sp',NS):
                if shape.find('p:txBody',NS) is None:continue
                xf=shape.find('p:spPr/a:xfrm',NS);off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
                x,y=int(off.get('x')),int(off.get('y'));w,h=int(ext.get('cx')),int(ext.get('cy'))
                if x<0 or y<0 or x+w>px(1280)+px(2) or y+h>px(720)+px(2):
                    raise ValueError(f'{s["id"]}: text box leaves the slide canvas')
        for name in z.namelist():
            if not name.endswith('.xml'):continue
            root=etree.fromstring(z.read(name))
            for el in root.iter():
                for attr in ('rot','dir','ang'):
                    if attr in el.attrib:
                        value=int(el.get(attr))
                        if not -(2**31)<=value<2**31:raise ValueError(f'OOXML angle overflow: {name}')

def render_actual(pptx,manifest,changed,cache,render_dir):
    if not changed:return
    render_dir.mkdir(parents=True,exist_ok=True)
    indices=[i for i,s in enumerate(manifest['slides'],1) if s['id'] in changed]
    options=json.dumps({'PageRange':{'type':'string','value':','.join(map(str,indices))}},separators=(',',':'))
    with tempfile.TemporaryDirectory(dir=render_dir) as temp:
        run([binary('soffice'),'-env:UserInstallation='+Path(temp).joinpath('lo-profile').as_uri(),'--headless','--convert-to','pdf:impress_pdf_Export:'+options,'--outdir',temp,pptx])
        pdf=Path(temp)/(pptx.stem+'.pdf')
        if not pdf.exists():raise RuntimeError('actual PPT render produced no PDF')
        prefix=Path(temp)/'page'
        run([binary('pdftoppm'),'-png','-scale-to-x','1280','-scale-to-y','720',pdf,prefix])
        pages=sorted(Path(temp).glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
        if len(pages)!=len(indices):raise RuntimeError('PPT render page count does not match requested pages')
        for page,index in zip(pages,indices):
            shutil.copyfile(page,cache/f'{manifest["slides"][index-1]["id"]}-final.png')
        shutil.copyfile(pdf,render_dir/'last-render.pdf')

def montage(manifest,cache,target):
    count=len(manifest['slides']);cols=min(2,count);width=640;height=360;gap=24;label=26
    rows=(count+cols-1)//cols
    canvas=Image.new('RGB',(gap+cols*(width+gap),gap+rows*(height+label+gap)), '#E8EBEF')
    draw=ImageDraw.Draw(canvas)
    for i,s in enumerate(manifest['slides']):
        x=gap+(i%cols)*(width+gap);y=gap+(i//cols)*(height+label+gap)
        with Image.open(cache/f'{s["id"]}-final.png') as image:canvas.paste(image.convert('RGB').resize((width,height)),(x,y))
        draw.text((x,y+height+5),f'{i+1:02d} / {s["id"]}',fill='#334155')
    canvas.save(target)

def package_sources(project,manifest,font_paths,target):
    text=('本项目包含逐页 SVG、可编辑文字与矢量对象、deck.json、使用的开放字体和许可。\n'
          '在另一台设备上保持排版：先安装 fonts/ 中的字体，再打开 PPTX 或 SVG。\n'
          '修改 SVG 的 text/图形或直接修改 PPT 原生对象。矢量图表不包含 Excel 数据工作表。\n'
          '用 PPT Agent 重建：python3 SKILL_DIR/scripts/deck.py build PROJECT_DIR\n')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(project/'deck.json','deck.json')
        for s in manifest['slides']:z.write(project/s['svg'],s['svg'])
        for file in font_paths:
            path=Path(file)
            # Only package the automatically provisioned OFL fonts, not arbitrary proprietary fonts.
            if path.parent==CACHE and (CACHE/'OFL.txt').is_file():z.write(path,'fonts/'+path.name)
        if any(Path(f).parent==CACHE for f in font_paths) and (CACHE/'OFL.txt').exists():
            z.write(CACHE/'OFL.txt','fonts/OFL.txt')
        z.writestr('使用说明.txt',text)

def build(project):
    build_dir=project/'build';out=project/'output';cache=build_dir/'cache'
    cache.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    report={'ok':False,'reviewed':False,'errors':[],'changed_slides':[],'slides':[]}
    try:
        manifest=load(project);keys,font_paths,fingerprint=context(project,manifest)
        report.update(fingerprint=fingerprint,fonts=font_paths)
        old_path=build_dir/'cache.json'
        old=json.loads(old_path.read_text()) if old_path.exists() else {}
        changed=[]
        for spec in manifest['slides']:
            sid=spec['id'];part=cache/f'{sid}.xml';stats_path=cache/f'{sid}.json'
            hit=(old.get(sid)==keys[sid] and all(p.exists() for p in
                 (part,stats_path,cache/f'{sid}-source.png',cache/f'{sid}-final.png')))
            if not hit:
                tree,stats=SvgConverter().convert(project/spec['svg'])
                part.write_bytes(etree.tostring(tree,encoding='utf-8'))
                write_json(stats_path,stats)
                run([node(),HERE/'preview.mjs',project/spec['svg'],cache/f'{sid}-source.png'])
                changed.append(sid)
            report['slides'].append({'id':sid,'cached':hit,'counts':json.loads(stats_path.read_text()),
                                     'source_preview':str(cache/f'{sid}-source.png'),'ppt_preview':str(cache/f'{sid}-final.png')})
        report['changed_slides']=changed
        pptx=out/'presentation.pptx';container=build_dir/'container.pptx'
        previous_path=build_dir/'report.json'
        if not changed and previous_path.exists():
            previous=json.loads(previous_path.read_text())
            intact=(previous.get('ok') and previous.get('fingerprint')==fingerprint
                    and all((out/name).is_file() and digest((out/name).read_bytes())==sha
                            for name,sha in previous.get('outputs',{}).items())
                    and all(digest((cache/f'{sid}-final.png').read_bytes())==sha
                            for sid,sha in previous.get('render_hashes',{}).items()))
            if intact:
                previous['changed_slides']=[]
                for slide in previous['slides']:slide['cached']=True
                write_json(previous_path,previous)
                print(json.dumps({'ok':True,'reviewed':previous['reviewed'],'changed_slides':[],
                                  'errors':[],'reused_build':True},ensure_ascii=False))
                return 0
        run([node(),HERE/'container.mjs',project/'deck.json',container])
        with zipfile.ZipFile(container) as zin,zipfile.ZipFile(pptx,'w',zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data=zin.read(item.filename)
                match=re.fullmatch(r'ppt/slides/slide(\d+)\.xml',item.filename)
                if match:
                    spec=manifest['slides'][int(match[1])-1];root=etree.fromstring(data)
                    sp=root.find('.//p:spTree',NS)
                    for child in list(sp):
                        if local_name(child.tag) not in ('nvGrpSpPr','grpSpPr'):sp.remove(child)
                    compiled=etree.fromstring((cache/f'{spec["id"]}.xml').read_bytes())
                    for child in compiled:sp.append(child)
                    data=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
                zout.writestr(item,data)
        technical=validate_pptx(pptx,len(manifest['slides']));report['pptx']=technical
        if not technical['ok']:raise ValueError('; '.join(technical['errors']))
        if technical['summary']['pictures']:raise ValueError('PPTX contains pictures in all-vector mode')
        verify_content(pptx,manifest,project);report['text_fidelity']=True
        render_actual(pptx,manifest,changed,cache,build_dir/'render')
        montage(manifest,cache,build_dir/'preview.png')
        shutil.copyfile(build_dir/'preview.png',out/'preview.png')
        package_sources(project,manifest,font_paths,out/'svg-source.zip')
        report['rendered']=True;report['ok']=True
        # Each delivery route owns its files; HTML rendering must not invalidate PPT review.
        report['outputs']={name:digest((out/name).read_bytes())
                           for name in ('presentation.pptx','svg-source.zip','preview.png')}
        report['render_hashes']={s['id']:digest((cache/f'{s["id"]}-final.png').read_bytes()) for s in manifest['slides']}
        write_json(old_path,keys)
        review_path=build_dir/'review.json'
        if review_path.exists():
            review=json.loads(review_path.read_text())
            report['reviewed']=review.get('fingerprint')==fingerprint and review.get('outputs')==report['outputs']
    except Exception as exc:
        report['errors'].append(str(exc))
    write_json(build_dir/'report.json',report)
    print(json.dumps({k:report[k] for k in ('ok','reviewed','changed_slides','errors')},ensure_ascii=False))
    return 0 if report['ok'] else 1

def approve(project,note):
    report_path=project/'build/report.json';report=json.loads(report_path.read_text())
    manifest=load(project);keys,fonts,fingerprint=context(project,manifest)
    if not report.get('ok') or not report.get('rendered'):raise ValueError('current build has not passed technical/render checks')
    if report.get('fingerprint')!=fingerprint:raise ValueError('source or dependencies changed; rebuild and inspect first')
    if not note.strip():raise ValueError('record what was actually inspected')
    for filename,sha in report['outputs'].items():
        if digest((project/'output'/filename).read_bytes())!=sha:raise ValueError('output changed after validation')
    for sid,sha in report['render_hashes'].items():
        if digest((project/'build/cache'/f'{sid}-final.png').read_bytes())!=sha:raise ValueError('render changed after validation')
    write_json(project/'build/review.json',{'fingerprint':fingerprint,'outputs':report['outputs'],'note':note,'time':time.time()})
    report['reviewed']=True;write_json(report_path,report)
    print(json.dumps({'ok':True,'reviewed':True},ensure_ascii=False))

def edit(project,slide_id,object_id,text):
    manifest=load(project);matches=[s for s in manifest['slides'] if s['id']==slide_id]
    if len(matches)!=1:raise ValueError('slide id does not exist')
    path=project/matches[0]['svg'];parser=etree.XMLParser(resolve_entities=False,no_network=True)
    tree=etree.parse(str(path),parser);nodes=tree.xpath('//*[@id=$id]',id=object_id)
    if len(nodes)!=1 or local_name(nodes[0].tag) not in ('text','tspan'):
        raise ValueError('text id must resolve to exactly one text/tspan object')
    if len(nodes[0]):raise ValueError('edit individual tspan ids instead of overwriting a structured text group')
    nodes[0].text=text
    tree.write(str(path),encoding='utf-8',xml_declaration=True)
    print(json.dumps({'edited_slide':slide_id,'object':object_id},ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for command in ('build','approve','edit'):
        p=sub.add_parser(command);p.add_argument('project',type=Path)
        if command=='approve':p.add_argument('--note',required=True)
        if command=='edit':
            p.add_argument('--slide',required=True);p.add_argument('--id',required=True);p.add_argument('--text',required=True)
    args=parser.parse_args();project=args.project.resolve()
    try:
        if args.command=='build':return build(project)
        if args.command=='approve':approve(project,args.note)
        if args.command=='edit':edit(project,args.slide,args.id,args.text)
        return 0
    except Exception as exc:print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
