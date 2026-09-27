import { chromium } from '/Users/jadelezzi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root=path.dirname(fileURLToPath(import.meta.url));
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--hide-scrollbars','--font-render-hinting=none']});
const context=await browser.newContext({viewport:{width:1280,height:720},deviceScaleFactor:1.5,colorScheme:'light',reducedMotion:'reduce',locale:'fr-FR'});
const page=await context.newPage();
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
// Only the isolated fixture server is used. No live product data is fetched.
await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.hostname==='127.0.0.1')return route.continue();
  return route.abort();
});
try {
  await page.goto('http://127.0.0.1:8034/',{waitUntil:'networkidle'});
  await page.locator('.article-card').nth(23).waitFor({state:'attached'});
  // Capture the final loaded appearance, not the image opacity transition.
  await page.addStyleTag({content:'.article-visual img { transition: none !important; }'});
  await page.locator('img').evaluateAll(images=>images.forEach(img=>{img.loading='eager';}));
  await page.evaluate(async()=>{
    await document.fonts.ready;
    await Promise.all([...document.images].map(img=>img.complete?Promise.resolve():new Promise(resolve=>{img.onload=resolve;img.onerror=resolve;})));
    await Promise.all([...document.images].map(img=>img.decode().catch(()=>{})));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  });
  const metrics=await page.evaluate(()=>({
    cssWidth:innerWidth,cssHeight:innerHeight,scale:devicePixelRatio,
    scrollHeight:document.scrollingElement.scrollHeight,
    footerTop:document.querySelector('.paper-footer').getBoundingClientRect().top+scrollY,
    articles:document.querySelectorAll('.article-card').length,
    loadedImages:document.querySelectorAll('.article-visual.is-loaded').length,
    sections:[...document.querySelectorAll('.paper-navigation button')].map(x=>x.textContent),
    alerts:[...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent).filter(Boolean),
    fixedVisible:[...document.querySelectorAll('body *')].filter(el=>['fixed','sticky'].includes(getComputedStyle(el).position)&&el.getBoundingClientRect().width&&el.getBoundingClientRect().height&&getComputedStyle(el).opacity!=='0'&&getComputedStyle(el).visibility!=='hidden').map(el=>({tag:el.tagName,classes:el.className,text:el.textContent.slice(0,80)})),
  }));
  if(errors.length||metrics.alerts.length)throw Error(JSON.stringify({errors,alerts:metrics.alerts}));
  // Keep at least 300 CSS pixels before the footer below the last viewport.
  metrics.scrollEnd=Math.min(1250,metrics.footerTop-metrics.cssHeight-300);
  if(metrics.scrollEnd<500)throw Error('Not enough real page content for the shot');
  await page.waitForFunction(()=>[...document.querySelectorAll('.article-visual.is-loaded img')].every(img=>getComputedStyle(img).opacity==='1'));
  await page.screenshot({path:path.join(root,'page-complete.png'),fullPage:true,animations:'disabled'});
  await page.screenshot({path:path.join(root,'capture-debut.png'),animations:'disabled'});
  await page.evaluate(y=>window.scrollTo(0,y),Math.round(metrics.scrollEnd));
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await page.screenshot({path:path.join(root,'capture-fin.png')});
  await fs.writeFile(path.join(root,'capture-metadata.json'),JSON.stringify({...metrics,errors},null,2));
  console.log(JSON.stringify(metrics,null,2));
}finally{
  await context.close();
  await browser.close();
}
