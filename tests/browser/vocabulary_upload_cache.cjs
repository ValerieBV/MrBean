// Regression: old CSS/JS at the old URLs must not hide the photo picker.
const {chromium}=require('playwright');
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('node:assert/strict');
const {execFileSync,spawn}=require('child_process');
const root=path.resolve(__dirname,'../..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mrbean-photo-cache-'));
const output=process.env.MRBEAN_QA_OUTPUT||temporary;fs.mkdirSync(output,{recursive:true});
const python=process.env.MRBEAN_PYTHON||path.join(root,'.venv','bin','python');
const env={...process.env,DJANGO_DEBUG:'true',OPENAI_API_KEY:'',DJANGO_DB_PATH:path.join(temporary,'test.sqlite3'),DJANGO_MEDIA_ROOT:path.join(temporary,'media')};
const base='http://127.0.0.1:8767';let server,browser;
(async()=>{
 for(const args of [['migrate','--noinput'],['seed_demo','--password','DemoLocal123!']])execFileSync(python,['manage.py',...args],{cwd:root,env,stdio:'pipe'});
 const task=execFileSync(python,['manage.py','shell','-c',"from dashboard.models import LearningTask; print(LearningTask.objects.get(learner__username='demo_student',assignment__lesson__skill='vocabulary').pk)"],{cwd:root,env,encoding:'utf8'}).trim().split('\n').at(-1);
 const log=fs.openSync(path.join(output,'server.log'),'w');
 server=spawn(python,['manage.py','runserver','127.0.0.1:8767','--noreload'],{cwd:root,env,stdio:['ignore',log,log]});
 for(let i=0;i<100;i++){try{if((await fetch(base+'/accounts/login/')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,executablePath:process.env.MRBEAN_CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 const context=await browser.newContext({viewport:{width:1440,height:950}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/accounts/login/');await page.locator('[name=username]').fill('demo_student');await page.locator('[name=password]').fill('DemoLocal123!');
 await Promise.all([page.waitForURL('**/hoc-tap/'),page.getByRole('button',{name:'Đăng nhập hệ thống',exact:true}).click()]);
 const staleCSS=fs.readFileSync(path.join(root,'core/static/core/palette.css'),'utf8').split('\n').filter(line=>!line.includes('.vocabulary-')).join('\n');
 let staleHits=0;
 await page.route('**/static/core/palette.css',r=>{staleHits++;return r.fulfill({contentType:'text/css',body:staleCSS});});
 await page.route('**/static/submissions/submit.js',r=>{staleHits++;return r.fulfill({contentType:'text/javascript',body:'/* Cached pre-photo script. */'});});
 await page.evaluate(async()=>{await Promise.all(['/static/core/palette.css','/static/submissions/submit.js'].map(url=>fetch(url).then(r=>r.text())));});
 await page.goto(base+`/hoc-tap/tasks/${task}/`);
 assert.equal(await page.locator('.vocabulary-upload').evaluate(el=>getComputedStyle(el).borderTopStyle),'dashed');
 assert.equal(await page.locator('#chooseImages').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(42, 26, 14)');
 assert(await page.locator('#chooseImages').isVisible());assert(!(await page.locator('#imagePickerFallback').isVisible()));
 const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Chọn ảnh bài làm',exact:true}).click();
 const png=execFileSync(python,['-c',"import io,sys; from PIL import Image; b=io.BytesIO(); Image.new('RGB',(100,60),'white').save(b,'PNG'); sys.stdout.buffer.write(b.getvalue())"]);
 await (await chooser).setFiles({name:'bai-tu-vung.png',mimeType:'image/png',buffer:png});
 assert.equal(await page.locator('#imagePreviews img').count(),1);
 for(const width of [1440,1024,768,390]){
  await page.setViewportSize({width,height:950});if(width<992)await page.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.locator('#vocabularySubmitTitle').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,`photo-frame-${width}.png`)});
 }
 await page.getByRole('button',{name:/^Bỏ ảnh 1:/}).click();
 const audit=await new (require('@axe-core/playwright').default)({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();assert.equal(audit.violations.length,0,JSON.stringify(audit.violations.map(v=>v.id)));
 await page.route('**/static/submissions/submit.js?*',r=>r.fulfill({contentType:'text/javascript',body:'/* Enhancement unavailable. */'}));
 await page.reload();assert(await page.locator('#images').isVisible());assert(!(await page.locator('#chooseImages').isVisible()));
 assert.equal(errors.length,0,JSON.stringify(errors));assert.equal(staleHits,2);
 const result={passed:true,staleResponses:staleHits,viewports:[1440,1024,768,390],nativeFallback:true,accessibilityViolations:0,browserErrors:errors};
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(error=>{console.error(error.stack);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
