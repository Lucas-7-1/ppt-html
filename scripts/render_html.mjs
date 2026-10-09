// Actual local browser rendering; screenshots are evidence, never editable slide content.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {loadModule} from './runtime.mjs';
const project=path.resolve(process.argv[2]||'.');
const input=path.join(project,'output/presentation.html'),folder=path.join(project,'build/html');
const {chromium}=loadModule('playwright'),sharp=loadModule('sharp');
const hash=b=>createHash('sha256').update(b).digest('hex');
await fs.mkdir(folder,{recursive:true});
const options={headless:true};
if(process.env.PPT_AGENT_BROWSER)options.executablePath=process.env.PPT_AGENT_BROWSER;
if(process.env.PPT_AGENT_BROWSER_ARGS)options.args=JSON.parse(process.env.PPT_AGENT_BROWSER_ARGS);
const browser=await chromium.launch(options);
const page=await browser.newPage({viewport:{width:1600,height:1020},deviceScaleFactor:1});
const errors=[],findings=[],renderHashes={},network=[],interactions=[];
page.on('pageerror',error=>errors.push(error.message));
await page.route(/^https?:/,route=>{network.push(route.request().url());return route.abort();});
const files=[];
try{
  await page.goto(pathToFileURL(input).href);
  await page.evaluate(()=>document.fonts.ready);
  await page.emulateMedia({reducedMotion:'reduce'});
  const count=await page.locator('#deck > .slide').count();
  if(!count)throw new Error('No authored slides found');
  for(const mode of ['desktop','mobile']){
    await page.setViewportSize(mode==='desktop'?{width:1600,height:1020}:{width:390,height:844});
    for(let i=0;i<count;i++){
      await page.evaluate(i=>{location.hash='#'+(i+1)},i);
      await page.waitForFunction(i=>document.querySelectorAll('#deck > .slide')[i].classList.contains('active'),i);
      const file=path.join(folder,`${mode}-${String(i+1).padStart(2,'0')}.png`);
      await page.locator('#viewport').screenshot({path:file});
      renderHashes[file]=hash(await fs.readFile(file));
      if(mode==='desktop')files.push(file);
      if(mode==='mobile'){
        const dimensions=await page.locator('#viewport').evaluate(e=>({height:e.clientHeight,total:e.scrollHeight}));
        for(let offset=dimensions.height,part=2;offset<dimensions.total;offset+=dimensions.height,part++){
          await page.locator('#viewport').evaluate((e,y)=>{e.scrollTop=y},offset);
          const continuation=path.join(folder,`mobile-${String(i+1).padStart(2,'0')}-${part}.png`);
          await page.locator('#viewport').screenshot({path:continuation});
          renderHashes[continuation]=hash(await fs.readFile(continuation));
        }
        await page.locator('#viewport').evaluate(e=>{e.scrollTop=0});
      }
      const issue=await page.evaluate(()=>{
        const s=document.querySelector('.slide.active'),b=s.getBoundingClientRect();
        return [...s.querySelectorAll('.editable')].filter(e=>e.getClientRects().length).flatMap(e=>{
          const r=e.getBoundingClientRect();
          const outside=r.left<b.left-2||r.top<b.top-2||r.right>b.right+2||r.bottom>b.bottom+2;
          const style=getComputedStyle(e);
          // CJK glyph bounds can exceed a tight line box without being clipped.
          const overflow=e.scrollWidth>e.clientWidth+2||(style.overflowY!=='visible'&&e.scrollHeight>e.clientHeight+2);
          return outside||overflow?[{text:e.textContent.slice(0,80),outside,overflow}]:[];
        });
      });
      if(issue.length)findings.push({mode,page:i+1,issues:issue});
    }
  }
  await page.setViewportSize({width:1600,height:1020});
  async function check(name,action){
    try{await action();interactions.push({name,ok:true});}
    catch(error){interactions.push({name,ok:false,error:error.message});errors.push(name+': '+error.message);}
  }
  await check('keyboard navigation',async()=>{
    await page.keyboard.press('Home');
    if(count>1){await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>location.hash==='#2');}
    await page.keyboard.press('Home');await page.waitForFunction(()=>location.hash==='#1');
  });
  await check('directory and notes',async()=>{
    await page.locator('#toc').click();
    if(await page.locator('.directory-card').count()!==count)throw new Error('Directory count differs');
    await page.locator('.directory-card').last().click();
    await page.locator('#notes').click();
    await page.locator('.notes-backdrop.open').waitFor();
    await page.keyboard.press('Escape');
    if(await page.locator('.notes-backdrop.open').count())throw new Error('Notes did not close');
  });
  await check('edit, download and reopen',async()=>{
    await page.keyboard.press('Home');await page.locator('#edit').click();
    const editable=page.locator('.slide.active .editable').first();
    const before=await editable.innerHTML();
    const changed=(await editable.innerText())+' ·';
    await editable.fill(changed);
    const downloaded=page.waitForEvent('download');await page.locator('#save').click();
    const copy=path.join(folder,'edited-copy.html');await (await downloaded).saveAs(copy);
    if(!(await fs.readFile(copy,'utf8')).includes('SIL OPEN FONT LICENSE'))throw new Error('Font license missing in saved copy');
    try{await page.goto(pathToFileURL(copy).href);await page.evaluate(()=>document.fonts.ready);
      if(await page.locator('.slide.active .editable').first().innerText()!==changed)throw new Error('Edited text did not persist');
      if(await page.locator('[contenteditable]').count())throw new Error('Saved copy retained editing mode');
    }finally{await page.goto(pathToFileURL(input).href);await page.evaluate(()=>document.fonts.ready);}
  });
  await check('mobile swipe',async()=>{
    await page.setViewportSize({width:390,height:844});await page.keyboard.press('Home');
    if(count>1){
      await page.locator('#viewport').dispatchEvent('touchstart',{touches:[{identifier:0,clientX:300,clientY:300}]});
      await page.locator('#viewport').dispatchEvent('touchend',{changedTouches:[{identifier:0,clientX:100,clientY:302}]});
      await page.waitForFunction(()=>location.hash==='#2');
    }
  });
  await page.setViewportSize({width:1600,height:1020});await page.keyboard.press('Home');
  await page.pdf({path:path.join(folder,'presentation.pdf'),printBackground:true,preferCSSPageSize:true});
  const cols=Math.min(count,2),rows=Math.ceil(count/cols),w=640,h=360,g=22;
  const composite=await Promise.all(files.map(async(file,i)=>({input:await sharp(file).resize(w,h).png().toBuffer(),left:g+(i%cols)*(w+g),top:g+Math.floor(i/cols)*(h+g)})));
  const preview=path.join(project,'output/preview-html.png');
  await sharp({create:{width:g+cols*(w+g),height:g+rows*(h+g),channels:3,background:'#E7EAF0'}}).composite(composite).png().toFile(preview);
  renderHashes[preview]=hash(await fs.readFile(preview));
  const report={ok:!errors.length&&!findings.length&&!network.length,pages:count,html_sha256:hash(await fs.readFile(input)),errors,findings,network,interactions,render_hashes:renderHashes};
  await fs.writeFile(path.join(folder,'render.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({ok:report.ok,pages:count,errors,findings,network,interactions}));
  if(!report.ok)process.exitCode=1;
}finally{await browser.close();}
