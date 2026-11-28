// Staff can inspect supplemental OCR; learners only see confirmed results.
const {chromium}=require('playwright');
const AxeBuilder=require('@axe-core/playwright').default;
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('node:assert/strict');
const {execFileSync,spawn}=require('child_process');
const root=path.resolve(__dirname,'../..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mrbean-local-model-'));
const output=process.env.MRBEAN_QA_OUTPUT||temporary;
fs.mkdirSync(output,{recursive:true});
const python=process.env.MRBEAN_PYTHON||(process.platform==='win32'?path.join(root,'.venv','Scripts','python.exe'):path.join(root,'.venv','bin','python'));
const env={...process.env,DJANGO_DEBUG:'true',OPENAI_API_KEY:'',AI_LOCAL_ENABLED:'false',
 DJANGO_DB_PATH:path.join(temporary,'test.sqlite3'),DJANGO_MEDIA_ROOT:path.join(temporary,'media')};
const base='http://127.0.0.1:8768';
let server,browser;
(async()=>{
 for(const args of [['migrate','--noinput'],['seed_demo','--password','DemoLocal123!']])
  execFileSync(python,['manage.py',...args],{cwd:root,env,stdio:'pipe'});
 const jobID=execFileSync(python,['manage.py','shell','-c',String.raw`
from dashboard.models import LearningTask
from ai_core.models import GradingJob
task=LearningTask.objects.get(learner__username='demo_student',assignment__lesson__skill='vocabulary')
result={'needs_manual':False,'complete':True,'feedback':'Đã đối chiếu ảnh gốc, đủ số lượt viết.',
 'details':[{'word':word,'required':3,'observed':3,'missing':0} for word in task.assignment.rubric['words']],
 'expected_total':9,'matched_total':9,
 'recognition':{'kind':'vocabulary','status':'partial','used':True,'advisory_only':True,'exhaustive':False,
 'recognizer':'local_trocr','text':'LOCAL_ONLY_RECOGNITION_MARKER\n'+'department'*40+'\n<script>window.__ocrExecuted=true</script>'}}
job=GradingJob.objects.create(task=task,submission_key='local-browser-review',kind='vocabulary',status='ai_reviewed',
 rubric_snapshot=task.assignment.rubric,result=result,grading_method='local_openai')
print(job.pk)
`],{cwd:root,env,encoding:'utf8'}).trim().split('\n').at(-1);
 const log=fs.openSync(path.join(output,'server.log'),'w');
 server=spawn(python,['manage.py','runserver','127.0.0.1:8768','--noreload'],{cwd:root,env,stdio:['ignore',log,log]});
 for(let i=0;i<100;i++){
  try{if((await fetch(base+'/accounts/login/')).ok)break;}catch{}
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 browser=await chromium.launch({headless:true,executablePath:process.env.MRBEAN_CHROMIUM_PATH,
  args:['--no-sandbox','--disable-dev-shm-usage']});
 const errors=[],audits=[];
 async function session(username){
  const context=await browser.newContext({viewport:{width:1440,height:950}});
  const page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base+'/accounts/login/');
  await page.locator('[name=username]').fill(username);
  await page.locator('[name=password]').fill('DemoLocal123!');
  await Promise.all([page.waitForURL(username==='demo_student'?'**/hoc-tap/':'**/dashboard/'),
   page.getByRole('button',{name:'Đăng nhập hệ thống',exact:true}).click()]);
  await page.goto(base+`/hoc-tap/results/${jobID}/`);
  return page;
 }
 const teacher=await session('demo_teacher');
 for(const width of [1440,1024,768,390]){
  await teacher.setViewportSize({width,height:950});
  if(width<992)await teacher.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);
  const panel=teacher.locator('[data-local-recognition]');
  await panel.locator('details').evaluate(element=>{element.open=true;});
  await panel.scrollIntoViewIfNeeded();
  assert(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow ${width}`);
  assert.equal(await teacher.evaluate(()=>window.__ocrExecuted),undefined);
  assert.match(await panel.innerText(),/chỉ bao gồm một phần/);
  const audit=await new AxeBuilder({page:teacher}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  assert.equal(audit.violations.length,0,JSON.stringify(audit.violations.map(v=>v.id)));
  audits.push({width,violations:0});
  await teacher.screenshot({path:path.join(output,`local-model-teacher-${width}.png`)});
 }
 const manager=await session('demo_manager');
 assert.equal(await manager.locator('[data-local-recognition]').count(),1);
 assert.equal(await manager.locator('#reviewForm').count(),0);
 const student=await session('demo_student');
 assert.equal(await student.locator('[data-local-recognition]').count(),0);
 assert(!(await student.content()).includes('LOCAL_ONLY_RECOGNITION_MARKER'));
 let detail=await student.request.get(base+`/ai/jobs/${jobID}/`);
 assert.equal(detail.status(),200);
 assert(!JSON.stringify(await detail.json()).includes('LOCAL_ONLY_RECOGNITION_MARKER'));
 await teacher.locator('[name=completion_status]').selectOption('complete');
 await teacher.locator('[name=feedback]').fill('Đã xem ảnh và xác nhận hoàn thành.');
 await teacher.getByRole('button',{name:'Xác nhận kết quả',exact:true}).click();
 await teacher.waitForFunction(()=>!document.getElementById('reviewForm'));
 await student.reload();
 assert.equal(await student.locator('[data-completion-status]').getAttribute('data-completion-status'),'complete');
 assert.equal(await student.locator('[data-local-recognition]').count(),0);
 assert(!(await student.content()).includes('LOCAL_ONLY_RECOGNITION_MARKER'));
 detail=await student.request.get(base+`/ai/jobs/${jobID}/`);
 assert.equal(detail.status(),200);
 assert(!JSON.stringify(await detail.json()).includes('LOCAL_ONLY_RECOGNITION_MARKER'));
 assert.equal(errors.length,0,JSON.stringify(errors));
 const result={passed:true,audits,managerReadOnly:true,learnerPrivacyBeforeAndAfterConfirmation:true,browserErrors:errors};
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result));
})().catch(error=>{console.error(error.stack);process.exitCode=1;}).finally(async()=>{
 if(browser)await browser.close();
 if(server)server.kill();
});
