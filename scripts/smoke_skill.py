#!/usr/bin/env python3
"""Exercise native editability, curves, incremental revision and failure gates."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from lxml import etree

HERE=Path(__file__).resolve().parent
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}

def command(*args,ok=True):
    result=subprocess.run([sys.executable,str(HERE/'deck.py'),*map(str,args)],capture_output=True,text=True)
    if (result.returncode==0)!=ok:raise AssertionError(result.stdout+'\n'+result.stderr)
    return result

def main():
    with tempfile.TemporaryDirectory(prefix='ppt-agent-smoke-') as work:
        project=Path(work);(project/'svg').mkdir()
        manifest={'title':'可编辑导出验证','slides':[{'id':'one','svg':'svg/01.svg','notes':'演示数据，仅用于导出测试','sources':['虚构测试材料']},
                 {'id':'two','svg':'svg/02.svg'}]}
        (project/'deck.json').write_text(json.dumps(manifest,ensure_ascii=False))
        start='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">'
        bg='<rect id="background" width="1280" height="720" fill="#F7F4EC"/>'
        text='<text id="value" x="80" y="160" font-family="Noto Sans SC" font-size="48" fill="#182821">结果 40%</text>'
        curve='<g id="evidence"><path id="arc" d="M80 340 A160 100 0 0 1 400 340" fill="none" stroke="#C74A2E" stroke-width="4"/><circle id="tiny-dot" cx="480" cy="340" r="1" fill="#182821"/></g>'
        for i in (1,2):(project/f'svg/0{i}.svg').write_text(start+bg+text+curve+'</svg>')
        command('build',project)
        report=json.loads((project/'build/report.json').read_text())
        assert report['ok'] and not report['reviewed'] and report['text_fidelity']
        assert report['pptx']['summary']['pictures']==0
        with zipfile.ZipFile(project/'output/presentation.pptx') as z:
            xml=etree.fromstring(z.read('ppt/slides/slide1.xml'))
            assert [t.text for t in xml.findall('.//a:t',NS)]==['结果 40%']
            assert xml.findall('.//p:grpSp',NS) and xml.findall('.//a:custGeom',NS)
            names={e.get('name') for e in xml.findall('.//p:cNvPr',NS)}
            assert {'value','evidence','arc','tiny-dot'}<=names
            notes=etree.fromstring(z.read('ppt/notesSlides/notesSlide1.xml'))
            note_text=''.join(notes.itertext())
            assert '演示数据，仅用于导出测试' in note_text and '虚构测试材料' in note_text
        other=[project/'svg/02.svg',project/'build/cache/two.xml',project/'build/cache/two-final.png']
        previous=[p.read_bytes() for p in other]
        command('edit',project,'--slide','one','--id','value','--text','结果 41%')
        command('approve',project,'--note','stale build must fail',ok=False)
        command('build',project)
        report=json.loads((project/'build/report.json').read_text())
        assert report['changed_slides']==['one']
        assert previous==[p.read_bytes() for p in other]
        reused=command('build',project)
        assert json.loads(reused.stdout)['reused_build']
        # An SVG wrapper containing a picture must fail instead of becoming a final deck.
        (project/'svg/01.svg').write_text(start+bg+text+'<image id="raster" x="0" y="0" width="1280" height="720" href="data:image/png;base64,AA=="/></svg>')
        command('build',project,ok=False)
        assert not json.loads((project/'build/report.json').read_text())['ok']
        print('PASS: native text/shapes/groups/arcs/tiny details; unchanged slide retained; stale review and raster rejected.')

if __name__=='__main__':main()
