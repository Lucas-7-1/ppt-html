#!/usr/bin/env python3
"""Compile self-contained SVG to editable DrawingML text, shapes and groups.

Used by deck.py; the PPT container is created with a JavaScript presentation engine.
Never rasterize, silently drop geometry, or author a python-pptx deck.
"""

import argparse
import base64
import binascii
import io
import json
import math
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from lxml import etree

# -------------------------------------------------------------------
# 常量
# -------------------------------------------------------------------
SVG_NS = 'http://www.w3.org/2000/svg'
XLINK_NS = 'http://www.w3.org/1999/xlink'
NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
}
EMU_PX = 9525
SLIDE_W = 12192000
SLIDE_H = 6858000

# CSS 完整命名颜色表（常用子集）
CSS_COLORS = {
    'aliceblue': 'f0f8ff', 'antiquewhite': 'faebd7', 'aqua': '00ffff',
    'aquamarine': '7fffd4', 'azure': 'f0ffff', 'beige': 'f5f5dc',
    'bisque': 'ffe4c4', 'black': '000000', 'blanchedalmond': 'ffebcd',
    'blue': '0000ff', 'blueviolet': '8a2be2', 'brown': 'a52a2a',
    'burlywood': 'deb887', 'cadetblue': '5f9ea0', 'chartreuse': '7fff00',
    'chocolate': 'd2691e', 'coral': 'ff7f50', 'cornflowerblue': '6495ed',
    'cornsilk': 'fff8dc', 'crimson': 'dc143c', 'cyan': '00ffff',
    'darkblue': '00008b', 'darkcyan': '008b8b', 'darkgoldenrod': 'b8860b',
    'darkgray': 'a9a9a9', 'darkgreen': '006400', 'darkgrey': 'a9a9a9',
    'darkkhaki': 'bdb76b', 'darkmagenta': '8b008b', 'darkolivegreen': '556b2f',
    'darkorange': 'ff8c00', 'darkorchid': '9932cc', 'darkred': '8b0000',
    'darksalmon': 'e9967a', 'darkseagreen': '8fbc8f', 'darkslateblue': '483d8b',
    'darkslategray': '2f4f4f', 'darkturquoise': '00ced1', 'darkviolet': '9400d3',
    'deeppink': 'ff1493', 'deepskyblue': '00bfff', 'dimgray': '696969',
    'dodgerblue': '1e90ff', 'firebrick': 'b22222', 'floralwhite': 'fffaf0',
    'forestgreen': '228b22', 'fuchsia': 'ff00ff', 'gainsboro': 'dcdcdc',
    'ghostwhite': 'f8f8ff', 'gold': 'ffd700', 'goldenrod': 'daa520',
    'gray': '808080', 'green': '008000', 'greenyellow': 'adff2f',
    'grey': '808080', 'honeydew': 'f0fff0', 'hotpink': 'ff69b4',
    'indianred': 'cd5c5c', 'indigo': '4b0082', 'ivory': 'fffff0',
    'khaki': 'f0e68c', 'lavender': 'e6e6fa', 'lawngreen': '7cfc00',
    'lemonchiffon': 'fffacd', 'lightblue': 'add8e6', 'lightcoral': 'f08080',
    'lightcyan': 'e0ffff', 'lightgoldenrodyellow': 'fafad2', 'lightgray': 'd3d3d3',
    'lightgreen': '90ee90', 'lightpink': 'ffb6c1', 'lightsalmon': 'ffa07a',
    'lightseagreen': '20b2aa', 'lightskyblue': '87cefa', 'lightslategray': '778899',
    'lightsteelblue': 'b0c4de', 'lightyellow': 'ffffe0', 'lime': '00ff00',
    'limegreen': '32cd32', 'linen': 'faf0e6', 'magenta': 'ff00ff',
    'maroon': '800000', 'mediumaquamarine': '66cdaa', 'mediumblue': '0000cd',
    'mediumorchid': 'ba55d3', 'mediumpurple': '9370db', 'mediumseagreen': '3cb371',
    'mediumslateblue': '7b68ee', 'mediumspringgreen': '00fa9a',
    'mediumturquoise': '48d1cc', 'mediumvioletred': 'c71585', 'midnightblue': '191970',
    'mintcream': 'f5fffa', 'mistyrose': 'ffe4e1', 'moccasin': 'ffe4b5',
    'navajowhite': 'ffdead', 'navy': '000080', 'oldlace': 'fdf5e6',
    'olive': '808000', 'olivedrab': '6b8e23', 'orange': 'ffa500',
    'orangered': 'ff4500', 'orchid': 'da70d6', 'palegoldenrod': 'eee8aa',
    'palegreen': '98fb98', 'paleturquoise': 'afeeee', 'palevioletred': 'db7093',
    'papayawhip': 'ffefd5', 'peachpuff': 'ffdab9', 'peru': 'cd853f',
    'pink': 'ffc0cb', 'plum': 'dda0dd', 'powderblue': 'b0e0e6',
    'purple': '800080', 'rebeccapurple': '663399', 'red': 'ff0000',
    'rosybrown': 'bc8f8f', 'royalblue': '4169e1', 'saddlebrown': '8b4513',
    'salmon': 'fa8072', 'sandybrown': 'f4a460', 'seagreen': '2e8b57',
    'seashell': 'fff5ee', 'sienna': 'a0522d', 'silver': 'c0c0c0',
    'skyblue': '87ceeb', 'slateblue': '6a5acd', 'slategray': '708090',
    'snow': 'fffafa', 'springgreen': '00ff7f', 'steelblue': '4682b4',
    'tan': 'd2b48c', 'teal': '008080', 'thistle': 'd8bfd8',
    'tomato': 'ff6347', 'turquoise': '40e0d0', 'violet': 'ee82ee',
    'wheat': 'f5deb3', 'white': 'ffffff', 'whitesmoke': 'f5f5f5',
    'yellow': 'ffff00', 'yellowgreen': '9acd32',
}

# 字体回退链
FONT_FALLBACK = {
    'PingFang SC': 'Microsoft YaHei',
    'SF Pro Display': 'Arial',
    'Helvetica Neue': 'Arial',
    'Helvetica': 'Arial',
    'system-ui': 'Microsoft YaHei',
    'sans-serif': 'Microsoft YaHei',
}


def px(v):
    return int(float(v) * EMU_PX)

def font_sz(svg_px):
    return max(100, int(float(svg_px) * 75))

def strip_unit(v):
    return re.sub(r'[a-z%]+', '', str(v))

def local_name(tag):
    """Return an XML local name and tolerate non-element nodes."""
    if not isinstance(tag, str):
        return ''
    return tag.rsplit('}', 1)[-1]

def natural_key(path):
    """Return a natural sort key for numbered slide filenames."""
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', path.stem)]

def sanitize_shape_name(value, fallback='Shape'):
    """Sanitize an SVG id for PowerPoint's selection pane."""
    raw = str(value or '').strip()
    cleaned = ''.join(
        char if (char.isalnum() or char in '._-') else '_'
        for char in raw
        if ord(char) >= 32
    )
    cleaned = re.sub(r'_+', '_', cleaned).strip('_. ')
    return (cleaned or fallback)[:240]

def resolve_font(ff_str):
    """解析 font-family 字符串，返回 PPT 可用字体。"""
    ff_str = ff_str.replace('&quot;', '').replace('"', '').replace("'", '')
    fonts = [f.strip() for f in ff_str.split(',') if f.strip()]
    for f in fonts:
        if f in FONT_FALLBACK:
            return FONT_FALLBACK[f]
        if f and f not in ('sans-serif', 'serif', 'monospace', 'system-ui'):
            return f
    return 'Microsoft YaHei'


# -------------------------------------------------------------------
# 颜色解析（完整 CSS 命名颜色）
# -------------------------------------------------------------------
def parse_color(s):
    if not s or s.strip() == 'none':
        return None
    s = s.strip()
    if s.startswith('url('):
        m = re.search(r'#([\w-]+)', s)
        return ('grad', m.group(1)) if m else None
    m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)', s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = float(m.group(4)) if m.group(4) else 1.0
        return (f'{r:02x}{g:02x}{b:02x}', int(a * 100000))
    if s.startswith('#'):
        h = s[1:]
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        return (h.lower().ljust(6, '0')[:6], 100000)
    c = CSS_COLORS.get(s.lower())
    return (c, 100000) if c else None


# -------------------------------------------------------------------
# OOXML 元素构造
# -------------------------------------------------------------------
def _el(tag, attrib=None, text=None, children=None):
    pre, local = tag.split(':') if ':' in tag else ('a', tag)
    el = etree.Element(f'{{{NS[pre]}}}{local}')
    if attrib:
        for k, v in attrib.items():
            el.set(k, str(v))
    if text is not None:
        el.text = str(text)
    for c in (children or []):
        if c is not None:
            el.append(c)
    return el

def _srgb(hex6, alpha=100000):
    el = _el('a:srgbClr', {'val': hex6})
    if alpha < 100000:
        el.append(_el('a:alpha', {'val': str(alpha)}))
    return el

def make_fill(fill_str, grads, opacity=1.0):
    c = parse_color(fill_str)
    if c is None:
        return _el('a:noFill')
    if c[0] == 'grad':
        gdef = grads.get(c[1])
        return _make_grad(gdef) if gdef else _el('a:noFill')
    hex6, alpha = c
    alpha = int(alpha * opacity)
    return _el('a:solidFill', children=[_srgb(hex6, alpha)])

def _make_grad(gdef):
    gs_lst = _el('a:gsLst')
    for stop in gdef['stops']:
        pos = int(stop['offset'] * 1000)
        sc = parse_color(stop['color_str'])
        if not sc or sc[0] == 'grad':
            continue
        hex6, alpha = sc
        alpha = int(alpha * stop.get('opacity', 1.0))
        gs_lst.append(_el('a:gs', {'pos': str(pos)}, children=[_srgb(hex6, alpha)]))

    if gdef.get('type') == 'radial':
        # 径向渐变
        path = _el('a:path', {'path': 'circle'}, children=[
            _el('a:fillToRect', {'l': '50000', 't': '50000', 'r': '50000', 'b': '50000'})
        ])
        return _el('a:gradFill', {'rotWithShape': '1'}, children=[gs_lst, path])
    else:
        # 线性渐变
        dx = gdef.get('x2', 1) - gdef.get('x1', 0)
        dy = gdef.get('y2', 1) - gdef.get('y1', 0)
        ang = int(math.degrees(math.atan2(dy, dx)) * 60000)
        if ang < 0:
            ang += 21600000
        lin = _el('a:lin', {'ang': str(ang), 'scaled': '0'})
        return _el('a:gradFill', children=[gs_lst, lin])

def make_line(stroke_str, stroke_w=1):
    c = parse_color(stroke_str)
    if not c or c[0] == 'grad':
        return None
    hex6, alpha = c
    w = max(1, int(float(strip_unit(stroke_w)) * 12700))
    return _el('a:ln', {'w': str(w)},
               children=[_el('a:solidFill', children=[_srgb(hex6, alpha)])])

def make_shape(sid, name, x, y, cx, cy, preset='rect',
               fill_el=None, line_el=None, rx=0, geom_el=None):
    sp = _el('p:sp')
    sp.append(_el('p:nvSpPr', children=[
        _el('p:cNvPr', {'id': str(sid), 'name': name}),
        _el('p:cNvSpPr'), _el('p:nvPr'),
    ]))
    sp_pr = _el('p:spPr')
    sp_pr.append(_el('a:xfrm', children=[
        _el('a:off', {'x': str(int(x)), 'y': str(int(y))}),
        _el('a:ext', {'cx': str(max(0, int(cx))), 'cy': str(max(0, int(cy)))}),
    ]))
    if geom_el is not None:
        sp_pr.append(geom_el)
    else:
        geom = _el('a:prstGeom', {'prst': preset})
        av = _el('a:avLst')
        if preset == 'roundRect' and rx > 0:
            shorter = max(min(cx, cy), 1)
            adj = min(50000, int(rx / (shorter / 2) * 50000))
            av.append(_el('a:gd', {'name': 'adj', 'fmla': f'val {adj}'}))
        geom.append(av)
        sp_pr.append(geom)
    sp_pr.append(fill_el if fill_el is not None else _el('a:noFill'))
    if line_el is not None:
        sp_pr.append(line_el)
    sp.append(sp_pr)
    return sp

def make_textbox(sid, name, x, y, cx, cy, paragraphs, anchor='t'):
    """paragraphs = [[{text,sz,bold,hex,alpha,font}, ...], ...]
    anchor: 't'=top, 'ctr'=center, 'b'=bottom
    """
    sp = _el('p:sp')
    sp.append(_el('p:nvSpPr', children=[
        _el('p:cNvPr', {'id': str(sid), 'name': name}),
        _el('p:cNvSpPr', {'txBox': '1'}), _el('p:nvPr'),
    ]))
    sp.append(_el('p:spPr', children=[
        _el('a:xfrm', children=[
            _el('a:off', {'x': str(int(x)), 'y': str(int(y))}),
            _el('a:ext', {'cx': str(max(0, int(cx))), 'cy': str(max(0, int(cy)))}),
        ]),
        _el('a:prstGeom', {'prst': 'rect'}, children=[_el('a:avLst')]),
        _el('a:noFill'), _el('a:ln', children=[_el('a:noFill')]),
    ]))
    tx = _el('p:txBody', children=[
        _el('a:bodyPr', {'wrap': 'none', 'lIns': '0', 'tIns': '0',
                         'rIns': '0', 'bIns': '0', 'anchor': anchor}),
        _el('a:lstStyle'),
    ])
    for runs in paragraphs:
        p_el = _el('a:p')
        # 段落属性: 行距=90%, 段前距=0, 段后距=0
        p_pr = _el('a:pPr')
        # Keep the font's natural metrics; percentage line spacing moves
        # the first baseline and breaks SVG fidelity, especially at large sizes.
        p_pr.append(_el('a:spcBef', children=[_el('a:spcPts', {'val': '0'})]))
        p_pr.append(_el('a:spcAft', children=[_el('a:spcPts', {'val': '0'})]))
        p_el.append(p_pr)
        for run in runs:
            rpr_a = {'lang': 'zh-CN', 'dirty': '0'}
            if run.get('sz'):
                rpr_a['sz'] = str(run['sz'])
            if run.get('bold'):
                rpr_a['b'] = '1'
            rpr = _el('a:rPr', rpr_a)
            rpr.append(_el('a:solidFill', children=[
                _srgb(run.get('hex', '000000'), run.get('alpha', 100000))
            ]))
            font = run.get('font', 'Microsoft YaHei')
            rpr.append(_el('a:latin', {'typeface': font}))
            rpr.append(_el('a:ea', {'typeface': font}))
            p_el.append(_el('a:r', children=[rpr, _el('a:t', text=run.get('text', ''))]))
        tx.append(p_el)
    sp.append(tx)
    return sp


# -------------------------------------------------------------------

def parse_gradients(self, root):
    self.grads = {}
    pct = lambda v: float(v.rstrip('%')) / 100 if '%' in str(v) else float(v)
    for g in (node for node in root.iter() if self._tag(node) == 'linearGradient'):
        gid = g.get('id')
        if not gid:
            continue
        stops = []
        for s in (child for child in g if self._tag(child) == 'stop'):
            off = s.get('offset', '0%')
            off = float(off.rstrip('%')) if '%' in off else float(off) * 100
            stops.append({'offset': off, 'color_str': s.get('stop-color', '#000'),
                          'opacity': float(s.get('stop-opacity', '1'))})
        self.grads[gid] = {
            'type': 'linear', 'stops': stops,
            'x1': pct(g.get('x1', '0%')), 'y1': pct(g.get('y1', '0%')),
            'x2': pct(g.get('x2', '100%')), 'y2': pct(g.get('y2', '100%')),
        }
    for g in (node for node in root.iter() if self._tag(node) == 'radialGradient'):
        gid = g.get('id')
        if not gid:
            continue
        stops = []
        for s in (child for child in g if self._tag(child) == 'stop'):
            off = s.get('offset', '0%')
            off = float(off.rstrip('%')) if '%' in off else float(off) * 100
            stops.append({'offset': off, 'color_str': s.get('stop-color', '#000'),
                          'opacity': float(s.get('stop-opacity', '1'))})
        self.grads[gid] = {'type': 'radial', 'stops': stops}


from fontTools.svgLib.path import parse_path
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fonts import text_metrics
from svg_validator import validate_svg_report, parse_safe_transform

INHERITED = ('fill','stroke','stroke-width','font-family','font-size','font-weight',
             'text-anchor','dominant-baseline','fill-opacity','stroke-opacity',
             'stroke-linecap','stroke-linejoin','color')

def normalize(root):
    def visit(el, inherited):
        own=dict(inherited)
        for key in INHERITED:
            if key in el.attrib: own[key]=el.get(key)
            elif key in own: el.set(key,own[key])
        for child in el: visit(child,own)
    visit(root,{'fill':'#000000','font-family':'Noto Sans SC','font-size':'24'})
    return root


def path_geometry(data):
    rec=RecordingPen(); parse_path(data,rec)
    bounds=BoundsPen(None);rec.replay(bounds)
    if bounds.bounds is None: raise ValueError('path has no visible geometry')
    x,y,x2,y2=bounds.bounds
    w=max(x2-x,.001);h=max(y2-y,.001)
    def point(p):return _el('a:pt',{'x':round((p[0]-x)/w*100000),'y':round((p[1]-y)/h*100000)})
    path=_el('a:path',{'w':100000,'h':100000})
    for op,points in rec.value:
        tags={'moveTo':'moveTo','lineTo':'lnTo','curveTo':'cubicBezTo','qCurveTo':'quadBezTo'}
        if op in tags:path.append(_el('a:'+tags[op],children=[point(p) for p in points]))
        elif op=='closePath':path.append(_el('a:close'))
        elif op!='endPath':raise ValueError(f'unsupported path operation {op}')
    geom=_el('a:custGeom',children=[_el('a:avLst'),_el('a:gdLst'),_el('a:ahLst'),
               _el('a:cxnLst'),_el('a:rect',{'l':'0','t':'0','r':'r','b':'b'}),
               _el('a:pathLst',children=[path])])
    return (x,y,w,h),geom


class SvgConverter:
    def __init__(self):
        self.sid=100;self.names=set();self.grads={}
        self.stats={'native_shapes':0,'text_shapes':0,'vector_shapes':0,'groups':0,'pictures':0,'skipped':0,
                    'errors':[],'shape_names':[],'fonts':[]}
        self._tag=lambda el:local_name(el.tag)

    def identity(self,el,fallback):
        self.sid+=1
        name=sanitize_shape_name(el.get('id') or f'{fallback}-{self.sid}',fallback)
        if name.casefold() in self.names:raise ValueError(f'duplicate object name: {name}')
        self.names.add(name.casefold());self.stats['shape_names'].append(name)
        return self.sid,name

    def convert(self,source):
        preflight=validate_svg_report(Path(source),pptx_safe=True)
        if preflight['errors']:raise ValueError('; '.join(preflight['errors']))
        parser=etree.XMLParser(resolve_entities=False,no_network=True)
        self.root=normalize(etree.parse(str(source),parser).getroot())
        parse_gradients(self,self.root)
        tree=_el('p:spTree')
        for child in self.root:self.walk(child,tree,0,0,1,1)
        if not self.stats['native_shapes']:raise ValueError('slide has no native shapes')
        return tree,self.stats

    def walk(self,el,parent,ox,oy,scale,opacity):
        tag=local_name(el.tag)
        if tag in ('defs','title','desc','metadata') or not tag:return
        if el.get('display')=='none' or el.get('visibility')=='hidden':return
        opacity*=float(el.get('opacity','1'))
        if opacity<=0:return
        if el.get('style') is not None:raise ValueError('inline CSS is not supported')
        if el.get('transform'):
            if tag not in ('g','use'):raise ValueError('apply leaf transforms to coordinates before exporting')
            transform=parse_safe_transform(el.get('transform'),tag)
            if transform is None:raise ValueError('unsupported transform')
            dx,dy,s=transform;ox+=dx*scale;oy+=dy*scale;scale*=s
        if tag=='g':
            sid,name=self.identity(el,'group')
            group=_el('p:grpSp',children=[_el('p:nvGrpSpPr',children=[_el('p:cNvPr',{'id':sid,'name':name}),
                    _el('p:cNvGrpSpPr'),_el('p:nvPr')]),_el('p:grpSpPr')])
            for child in el:self.walk(child,group,ox,oy,scale,opacity)
            xforms=group.xpath('./p:sp/p:spPr/a:xfrm|./p:grpSp/p:grpSpPr/a:xfrm',namespaces=NS)
            if not xforms:return
            boxes=[]
            for xf in xforms:
                off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
                x,y=int(off.get('x')),int(off.get('y'));w,h=int(ext.get('cx')),int(ext.get('cy'))
                boxes.append((x,y,x+w,y+h))
            x=min(b[0] for b in boxes);y=min(b[1] for b in boxes)
            w=max(1,max(b[2] for b in boxes)-x);h=max(1,max(b[3] for b in boxes)-y)
            group.find('p:grpSpPr',NS).append(_el('a:xfrm',children=[_el('a:off',{'x':x,'y':y}),
                _el('a:ext',{'cx':w,'cy':h}),_el('a:chOff',{'x':x,'y':y}),_el('a:chExt',{'cx':w,'cy':h})]))
            parent.append(group);self.stats['groups']+=1;return
        if tag=='use':
            href=el.get('href') or el.get('{'+XLINK_NS+'}href','')
            if not href.startswith('#'):raise ValueError('use must reference a local vector object')
            if href in getattr(self,'use_stack',[]):raise ValueError('recursive use')
            matches=self.root.xpath('//*[@id=$identifier]',identifier=href[1:])
            if len(matches)!=1:raise ValueError('use target does not resolve uniquely')
            import copy
            clone=copy.deepcopy(matches[0]);clone.set('id',el.get('id') or 'use-'+href[1:])
            self.use_stack=getattr(self,'use_stack',[])+[href]
            self.walk(clone,parent,ox+float(el.get('x',0))*scale,oy+float(el.get('y',0))*scale,scale,opacity)
            self.use_stack.pop();return
        if tag=='text':
            spans=[c for c in el if local_name(c.tag)=='tspan']
            if spans and (el.text or '').strip():raise ValueError('mixed direct text and tspan is not supported')
            cx=float(el.get('x',0));cy=float(el.get('y',0))
            for node in spans or [el]:
                for key in INHERITED:
                    if node.get(key) is None and el.get(key) is not None:node.set(key,el.get(key))
                cx=float(node.get('x',cx));cy=float(node.get('y',cy))+float(node.get('dy',0))
                self.text(node,parent,ox+cx*scale,oy+cy*scale,scale,opacity,el.get('id'))
            return
        if tag=='image':raise ValueError('image is forbidden in all-vector mode')
        if el.get('stroke-dasharray') or el.get('stroke-dashoffset'):
            raise ValueError('draw dash segments explicitly to preserve exact SVG geometry')
        sid,name=self.identity(el,tag)
        num=lambda key,default=0:float(strip_unit(el.get(key,str(default))))
        preset='rect';geom=None;radius=0
        if tag=='rect':
            x,y,w,h=num('x'),num('y'),num('width'),num('height')
            radius=num('rx',num('ry'));preset='roundRect' if radius else 'rect'
        elif tag in ('circle','ellipse'):
            rx=num('r') if tag=='circle' else num('rx');ry=rx if tag=='circle' else num('ry')
            x,y,w,h=num('cx')-rx,num('cy')-ry,rx*2,ry*2;preset='ellipse'
        elif tag in ('path','line','polygon','polyline'):
            if tag=='path':data=el.get('d','')
            elif tag=='line':data=f'M {num("x1")} {num("y1")} L {num("x2")} {num("y2")}'
            else:
                values=re.findall(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?',el.get('points',''))
                if len(values)<4 or len(values)%2:raise ValueError('invalid polygon/polyline coordinates')
                data='M '+' '.join(values[:2])+' L '+' '.join(values[2:])+(' Z' if tag=='polygon' else '')
            (x,y,w,h),geom=path_geometry(data)
        else:raise ValueError(f'unsupported visible element: {tag}')
        if w<=0 or h<=0:raise ValueError(f'{tag} has non-positive size')
        fill=make_fill(el.get('fill','none') if tag!='line' else 'none',self.grads,
                       opacity*float(el.get('fill-opacity','1')))
        line=make_line(el.get('stroke','none'),num('stroke-width',1)*scale)
        if line is None:line=_el('a:ln',children=[_el('a:noFill')])
        else:
            line.set('w',str(max(1,px(num('stroke-width',1)*scale))))
            line.set('cap',{'round':'rnd','square':'sq'}.get(el.get('stroke-linecap'),'flat'))
            for color in line.findall('.//a:srgbClr',NS):
                alpha=round(opacity*float(el.get('stroke-opacity','1'))*100000)
                if alpha<100000:color.append(_el('a:alpha',{'val':alpha}))
        shape=make_shape(sid,name,px(x*scale+ox),px(y*scale+oy),px(w*scale),px(h*scale),
                         preset=preset,fill_el=fill,line_el=line,rx=px(radius*scale),geom_el=geom)
        parent.append(shape);self.stats['native_shapes']+=1;self.stats['vector_shapes']+=1

    def text(self,node,parent,x,y,scale,opacity,hint):
        text=''.join(node.itertext())
        if not text.strip():return
        if node.get('textLength') is not None:raise ValueError('textLength changes character spacing; use real font metrics')
        size=float(strip_unit(node.get('font-size','24')))*scale
        family=node.get('font-family','Noto Sans SC').split(',')[0].strip(' \"\'')
        bold=node.get('font-weight') in ('bold','600','700','800','900')
        width,ascent,descent=text_metrics(text,family,size,bold)
        align=node.get('text-anchor','start')
        if align=='middle':x-=width/2
        elif align=='end':x-=width
        baseline=node.get('dominant-baseline','')
        # DrawingML's first baseline uses the em ascent; hhea values above
        # one em are CJK clipping reserves, not additional top padding.
        native_ascent=min(ascent,size)
        top=y-native_ascent
        if baseline in ('middle','central'):top=y-(ascent+descent)/2
        elif baseline in ('text-after-edge','after-edge'):top=y-native_ascent-descent
        elif baseline in ('text-before-edge','before-edge','hanging'):top=y
        elif baseline not in ('','auto','alphabetic'):raise ValueError(f'unsupported text baseline {baseline}')
        color=parse_color(node.get('fill','#000000'))
        if not color or color[0]=='grad':raise ValueError('editable text requires a solid fill')
        clone=etree.Element('text',id=node.get('id') or hint or f'text-{self.sid+1}')
        sid,name=self.identity(clone,'text')
        run={'text':text,'sz':round(size*.75*100),'bold':bold,'hex':color[0],
             'alpha':round(color[1]*opacity*float(node.get('fill-opacity','1'))),'font':family}
        # Width includes edit room; anchor location uses actual measured advance.
        shape=make_textbox(sid,name,px(x),px(top),px(width+size*.35),px(ascent+descent+size*.12),[[run]])
        parent.append(shape);self.stats['native_shapes']+=1;self.stats['text_shapes']+=1
        if family not in self.stats['fonts']:self.stats['fonts'].append(family)
