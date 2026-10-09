(()=>{
  'use strict';
  const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
  const slides=$$('#deck > .slide'),total=slides.length, viewport=$('#viewport');
  let index=0,editing=false,lastFocus=null,toastTimer;
  function fit(){
    const mobile=matchMedia('(max-width:760px) and (orientation:portrait)').matches;
    if(mobile){viewport.style.width='';viewport.style.height='';document.documentElement.style.setProperty('--scale',1);}
    else{const scale=Math.min((innerWidth-64)/1440,(innerHeight-156)/810,1.15);document.documentElement.style.setProperty('--scale',Math.max(.1,scale));viewport.style.width=1440*scale+'px';viewport.style.height=810*scale+'px';}
    $$('.directory-thumb').forEach(x=>{const el=x.shadowRoot?.querySelector('.slide');if(el)el.style.transform='scale('+x.clientWidth/1440+')';});
  }
  function toast(message){$('#toast').textContent=message;$('#toast').classList.add('open');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('open'),2500);}
  function show(i,animate=true){
    index=Math.max(0,Math.min(total-1,i));
    slides.forEach((s,n)=>{s.classList.toggle('active',n===index);s.classList.remove('entering');s.setAttribute('aria-hidden',String(n!==index));s.inert=n!==index;});
    if(animate){void slides[index].offsetWidth;slides[index].classList.add('entering');}
    $('#page-count').textContent=String(index+1).padStart(2,'0')+' / '+String(total).padStart(2,'0');
    $('#page-title').textContent=slides[index].dataset.title;
    $('#progress-bar').style.width=((index+1)/total*100)+'%';
    $('#prev').disabled=index===0;$('#next').disabled=index===total-1;
    if(location.hash!=='#'+(index+1))history.replaceState(null,'','#'+(index+1));
    updateNotes();$$('.directory-card').forEach((b,n)=>b.setAttribute('aria-current',String(n===index)));
    viewport.scrollTop=0;window.scrollTo({top:0,behavior:'instant'});
  }
  function updateNotes(){
    const s=slides[index];$('#notes-title').textContent=s.dataset.title;
    $('#notes-lead').textContent=s.dataset.claim||'';
    $('#notes-text').innerHTML='';
    const raw=s.querySelector('template.notes').content.cloneNode(true);$('#notes-text').appendChild(raw);
  }
  function closePanels(){
    $('#notes-backdrop').classList.remove('open');$('#directory').classList.remove('open');
    $('#notes-backdrop').setAttribute('aria-hidden','true');$('#directory').setAttribute('aria-hidden','true');
    $('#notes-backdrop').inert=true;$('#directory').inert=true;$('#app-shell').inert=false;
    if(lastFocus){lastFocus.focus();lastFocus=null;}
  }
  function openPanel(id){lastFocus=document.activeElement;const p=$(id);p.classList.add('open');p.setAttribute('aria-hidden','false');p.inert=false;$('#app-shell').inert=true;fit();p.querySelector('button').focus();}
  function makeDirectory(){
    const grid=$('#directory-grid');grid.innerHTML='';slides.forEach((s,n)=>{
      const b=document.createElement('button');b.className='directory-card';b.setAttribute('aria-label','第 '+(n+1)+' 页：'+s.dataset.title);b.setAttribute('aria-current',String(n===index));
      const box=document.createElement('div');box.className='directory-thumb';box.setAttribute('aria-hidden','true');
      const clone=s.cloneNode(true);clone.removeAttribute('id');clone.inert=true;clone.classList.remove('active','entering');clone.querySelectorAll('[id]').forEach(x=>x.removeAttribute('id'));clone.querySelectorAll('[contenteditable]').forEach(x=>x.removeAttribute('contenteditable'));
      const shadow=box.attachShadow({mode:'open'}),style=document.createElement('style');style.textContent=Array.from(document.styleSheets).flatMap(sheet=>Array.from(sheet.cssRules)).filter(rule=>rule.type!==CSSRule.MEDIA_RULE).map(rule=>rule.cssText).join('\n')+'.slide{display:block!important;inset:0;transform-origin:0 0}';shadow.append(style,clone);
      const label=document.createElement('span');label.className='directory-label';const num=document.createElement('b');num.textContent=String(n+1).padStart(2,'0');label.appendChild(num);label.appendChild(document.createTextNode(s.dataset.title));
      b.append(box,label);b.onclick=()=>{show(n);closePanels();};grid.appendChild(b);
    });
  }
  function editToggle(){editing=!editing;document.body.classList.toggle('editing',editing);$('#edit').setAttribute('aria-pressed',String(editing));$('#edit').textContent=editing?'完成编辑':'编辑';$('#save').hidden=!editing;slides.forEach(s=>s.querySelectorAll('.editable').forEach(x=>{if(editing)x.setAttribute('contenteditable','true');else x.removeAttribute('contenteditable');}));if(editing)toast('点击文字即可修改，改完请保存副本');}
  function saveCopy(){
    const root=document.documentElement.cloneNode(true);root.querySelector('body').classList.remove('editing');root.querySelectorAll('[contenteditable]').forEach(e=>e.removeAttribute('contenteditable'));root.querySelector('#edit').textContent='编辑';root.querySelector('#edit').setAttribute('aria-pressed','false');root.querySelector('#save').setAttribute('hidden','');root.querySelector('#directory-grid').innerHTML='';root.querySelector('#app-shell').removeAttribute('inert');root.querySelectorAll('.entering').forEach(x=>x.classList.remove('entering'));root.querySelectorAll('.open').forEach(x=>x.classList.remove('open'));
    const license=Array.from(document.childNodes).filter(n=>n.nodeType===8).map(n=>'<!--'+n.nodeValue+'-->').join('\n');
    const blob=new Blob(['<!doctype html>\n'+license+'\n'+root.outerHTML],{type:'text/html;charset=utf-8'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=(document.title.replace(/[\\/:*?"<>|]/g,'_')||'演示')+'_修改版.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已下载修改后的演示副本');
  }
  async function fullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();else toast('当前浏览器不支持全屏，可横屏观看');}catch{toast('当前浏览器未允许全屏，可横屏观看');}}
  $('#prev').onclick=()=>show(index-1);$('#next').onclick=()=>show(index+1);$('#notes').onclick=()=>openPanel('#notes-backdrop');$('#toc').onclick=()=>{makeDirectory();openPanel('#directory');};$('#edit').onclick=editToggle;$('#save').onclick=saveCopy;$('#fullscreen').onclick=fullscreen;
  $$('.panel-close').forEach(x=>x.onclick=closePanels);$('#notes-backdrop').onclick=e=>{if(e.target.id==='notes-backdrop')closePanels();};
  $('#copy-notes').onclick=async()=>{const t=$('#notes-title').textContent+'\n\n'+$('#notes-text').innerText;try{await navigator.clipboard.writeText(t);toast('已复制本页备注');}catch{const r=document.createRange();r.selectNodeContents($('#notes-text'));const s=getSelection();s.removeAllRanges();s.addRange(r);toast('已选中详解，可长按或使用系统复制');}};
  document.addEventListener('keydown',e=>{
    const panel=$('.notes-backdrop.open')||$('.directory.open');
    if(panel){if(e.key==='Escape'){e.preventDefault();closePanels();}if(e.key==='Tab'){const list=Array.from(panel.querySelectorAll('button')).filter(x=>!x.disabled),first=list[0],last=list.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}return;}
    if(e.target.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)||(e.key===' '&&e.target.tagName==='BUTTON'))return;
    if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(index+1);}else if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(index-1);}else if(e.key==='Home'){e.preventDefault();show(0);}else if(e.key==='End'){e.preventDefault();show(total-1);}else if(e.key.toLowerCase()==='n'){openPanel('#notes-backdrop');}else if(e.key.toLowerCase()==='g'){$('#toc').click();}else if(e.key.toLowerCase()==='f'){fullscreen();}else if(e.key.toLowerCase()==='e'){editToggle();}
  });
  let touchStart=null;viewport.addEventListener('touchstart',e=>{if(editing||e.touches.length!==1){touchStart=null;return;}const t=e.touches[0];touchStart={x:t.clientX,y:t.clientY};},{passive:true});viewport.addEventListener('touchend',e=>{if(!touchStart)return;const t=e.changedTouches[0],dx=t.clientX-touchStart.x,dy=t.clientY-touchStart.y;touchStart=null;if(Math.abs(dx)>70&&Math.abs(dx)>Math.abs(dy)*1.5)show(index+(dx<0?1:-1));},{passive:true});
  window.addEventListener('resize',fit);document.addEventListener('fullscreenchange',fit);window.addEventListener('hashchange',()=>{const n=parseInt(location.hash.slice(1),10);if(Number.isFinite(n))show(n-1,false);});
  $('#notes-backdrop').inert=true;$('#directory').inert=true;fit();const initial=parseInt(location.hash.slice(1),10);show(Number.isFinite(initial)?initial-1:0,false);document.fonts.ready.then(fit);
})();
