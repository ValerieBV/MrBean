'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync, spawn} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname,'../..'), temp = fs.mkdtempSync(path.join(os.tmpdir(),'mrbean-dash-'));
const out=path.resolve(process.env.MRBEAN_QA_OUTPUT || temp), python=process.env.MRBEAN_PYTHON || 'python';
const env={...process.env, DJANGO_DEBUG:'true', OPENAI_API_KEY:'', AI_LOCAL_ENABLED:'false',
  DJANGO_DB_PATH:path.join(temp,'db.sqlite3'),DJANGO_MEDIA_ROOT:path.join(temp,'media')};
const base='http://127.0.0.1:8782', password='DashboardLocal123!', errors=[], results=[];
let server,browser,lastPage;
function manage(...args){return execFileSync(python,['manage.py',...args],{cwd:root,env,encoding:'utf8'});}
const seed=`
from datetime import timedelta
from django.utils import timezone
from accounts.models import CustomUser
from courses.models import ClassRoom, Enrollment
from assignments.services import assign_to_class
from dashboard.models import LearningTask
from ai_core.models import GradingJob
from ai_core.services import enqueue_submission
from support.models import Conversation
now=timezone.now()
teacher=CustomUser.objects.get(username='demo_teacher')
a,b=[CustomUser.objects.get(username=n) for n in ('demo_student','demo_student2')]
for u,code in ((a,'DASH-01'),(b,'DASH-02')):
    u.first_name='Identical test name';u.student_code=code;u.save()
cls=ClassRoom.objects.get(class_code='DEMO-01')
quiz=a.learning_tasks.get(assignment__lesson__skill='listening')
job,_=enqueue_submission(task=quiz,submission_key='dash-listening',answers={str(q['id']):{'chosen':'B','short_answer':'My response'} for q in quiz.assignment.rubric['questions']})
assert job.completion_status=='complete'
for i in range(25):
    GradingJob.objects.create(task=quiz,kind='listening',status='graded',completion_status='complete',submission_key='dash-archive-'+str(i),submitted_at=now-timedelta(hours=1,minutes=i),rubric_snapshot=job.rubric_snapshot,result=job.result)
vocab=a.learning_tasks.get(assignment__lesson__skill='vocabulary')
GradingJob.objects.create(task=vocab,kind='vocabulary',status='manual',fallback_reason='ai_uncertain_evidence',submission_key='dash-manual',rubric_snapshot=vocab.assignment.rubric)
Conversation.objects.create(student=a,job=job,kind='knowledge',status='waiting',classroom=cls,recipient=teacher,recipient_role='teacher',escalated_at=now,subject='Test question')
b.learning_tasks.update(assigned_at=now-timedelta(days=14),due_at=now-timedelta(days=9))
other=CustomUser.objects.create_user('dash_other_teacher',role='teacher')
c=CustomUser.objects.create_user('dash_other_learner',role='student',student_code='DASH-03')
room=ClassRoom.objects.create(class_code='DASH-Z',name='Khác lớp',course=cls.course,teacher=other)
Enrollment.objects.create(student=c,classroom=room)
assign_to_class(actor=other,lesson=quiz.assignment.lesson,classroom=room,assigned_at=now-timedelta(days=22),due_at=now+timedelta(days=1),requires_previous=False)
`;
async function filled(p) {
  await p.waitForFunction(()=>document.getElementById('reportBody')?.getAttribute('aria-busy')==='false' &&
    !document.getElementById('reportBody').hidden && document.getElementById('reportStatus').textContent.startsWith('Cập nhật'));
}
async function filter(p,action) {
  const [response]=await Promise.all([p.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/metrics/') && r.request().resourceType()==='fetch'),action()]);
  assert.equal(response.status(),200);await filled(p);
}
async function checkWorkspace(p) {
  const {left,right,start,end,overflow}=await p.evaluate(()=>{
    const shell=document.querySelector('.app-main').getBoundingClientRect();
    const main=document.querySelector('#main-content').getBoundingClientRect();
    return {left:main.left,right:main.right,start:shell.left,end:shell.right,overflow:document.documentElement.scrollWidth-innerWidth};
  });
  assert(Math.abs(left-start)<2 && Math.abs(right-end)<2,'Dashboard must use the full workspace without applying the sidebar margin twice');
  assert(overflow<=1,'Horizontal page overflow');
}
async function settleSidebar(p,open){
  await p.waitForFunction(open=>{
    const panel=document.getElementById('sidebarMenu').getBoundingClientRect();
    return open ? Math.abs(panel.left)<1 : panel.right<=1;
  },open);
}
async function links(p) {
  const hrefs=await p.locator('#learning-report a:visible').evaluateAll(as=>[...new Set(as.map(a=>a.href))]);
  for(const href of hrefs){
    const url=new URL(href);assert.equal(url.origin,base);
    if(url.hash) assert(await p.locator(url.hash).count()>0,'missing '+url.hash);
    else assert.equal((await p.request.get(href)).status(),200,href);
  }
  return hrefs.length;
}
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  manage('migrate','--noinput');manage('seed_demo','--password',password);manage('shell','-c',seed);
  const log=fs.openSync(path.join(out,'server.log'),'w');
  server=spawn(python,['manage.py','runserver','127.0.0.1:8782','--noreload'],{cwd:root,env,stdio:['ignore',log,log]});
  let ready=false;
  for(let i=0;i<120;i++){try{ready=(await fetch(base+'/accounts/login/')).ok;}catch{} if(ready)break;await new Promise(r=>setTimeout(r,100));}
  assert(ready,'Test server unavailable');
  browser=await chromium.launch({headless:true,executablePath:process.env.MRBEAN_CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
  for(const role of ['admin','manager','teacher','student']){
    const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
    const p=await ctx.newPage();lastPage=p;let expected503=false;p.on('pageerror',err=>errors.push(role+': '+err.message));
    p.on('response',r=>{if(r.url().startsWith(base) && r.status()>=400 && !(expected503 && r.status()===503))errors.push(role+': '+r.status()+' '+r.url());});
    await p.goto(base+'/accounts/login/');await p.locator('[name=username]').fill('demo_'+role);
    await p.locator('[name=password]').fill(password);
    await Promise.all([p.waitForURL(role==='student'?'**/hoc-tap/':'**/dashboard/'),p.locator('button[type=submit]').click()]);
    await p.goto(base+'/dashboard/');await filled(p);
    assert(!((await p.locator('#learning-report').innerText()).includes('Identical test name')));
    await checkWorkspace(p);const availableLinks=await links(p);
    assert.equal(await p.locator('.lr-kpi').count(),4);
    if(role==='student'){
      assert.equal(await p.locator('#progress,#classChart,#aiChart').count(),0);
      assert.equal(await p.locator('#workCount').innerText(),'0');assert.equal(await p.locator('#reviewCount').innerText(),'1');
    }else{
      const expected=role==='teacher'?2:3;
      assert.equal(await p.locator('#progress .lr-row').count(),expected);
      assert.equal(await p.locator('#classChart button').count(),role==='teacher'?1:2);
      assert.equal(await p.locator('#queue .lr-row').count(),1);
      assert.equal(await p.locator('#support .lr-row').count(),role==='manager'?0:1);
      const caption=role==='manager'?'Xem bài nộp':'Mở để chấm';
      const review=await p.locator('#queue').getByRole('link',{name:caption,exact:true}).getAttribute('href');
      const html=await (await p.request.get(base+review)).text();
      assert.equal(html.includes('id="reviewForm"'),role!=='manager');
    }
    await filter(p,()=>p.locator('#historyPager').getByRole('button',{name:'Sau'}).click());
    assert.match(await p.locator('#historyPager').innerText(),/2\/2/);
    await filter(p,()=>p.locator('#historyPager').getByRole('button',{name:'Trước'}).click());
    await p.locator('#extraFilters summary').click();
    await filter(p,()=>p.locator('[name=scope]').selectOption('all'));
    assert.equal(new URL(p.url()).searchParams.get('scope'),'all');
    await filter(p,()=>p.locator('#filters button[type=submit]').click());
    await filter(p,()=>p.locator('#resetFilters').click());
    if(role==='admin'){
      await filter(p,()=>p.locator('#priorityAction [data-cross]').click());
      assert.equal(new URL(p.url()).searchParams.get('stage'),'review');
      assert.equal(new URL(p.url()).searchParams.get('ai'),'manual');
      await filter(p,()=>p.locator('#resetFilters').click());
      expected503=true;
      await p.route('**/dashboard/metrics/**',route=>route.fulfill({status:503,body:'offline'}),{times:1});
      await p.locator('.lr-kpi[data-value=submitted]').click();
      await p.locator('#retry').waitFor({state:'visible'});
      assert(await p.locator('#reportBody').isHidden());expected503=false;
      await filter(p,()=>p.locator('#retry').click());
      await filter(p,()=>p.locator('#resetFilters').click());
    }
    await filter(p,()=>p.locator('#skillChart [data-value=listening]').click());
    assert.equal(new URL(p.url()).searchParams.get('skill'),'listening');
    assert.equal(await p.locator('#skillChart button').count(),1);
    assert.equal(await p.locator('#stageChart [data-value=review]').count(),0);
    await filter(p,()=>p.locator('#stageChart [data-value=complete]').click());
    assert.equal(await p.locator('#tasks .lr-row').count(),1);assert.equal(await p.locator('#rate').innerText(),'100%');
    assert.equal(await p.locator('#weekChart button').count(),1);
    await filter(p,()=>p.locator('#weekChart button').click());
    assert(new URL(p.url()).searchParams.has('week'));
    const csv=await (await p.request.get(await p.locator('#exportLink').evaluate(a=>a.href))).text();
    assert(csv.includes('DASH-01') && !csv.includes('DASH-02') && !csv.includes('Identical test name'));
    await filter(p,()=>p.getByRole('button',{name:/^Bỏ bộ lọc Tuần từ:/}).click());
    await filter(p,()=>p.locator('#resetFilters').click());
    if(role!=='student'){
      await filter(p,()=>p.locator('#classChart button').filter({hasText:'DEMO-01'}).click());
      const saved=p.url();
      await p.locator('#risks').getByRole('link',{name:'Xem bài quá hạn',exact:true}).click();await filled(p);
      assert.equal(new URL(p.url()).searchParams.get('focus'),'overdue');assert.equal(await p.locator('#tasks .lr-row').count(),2);
      await p.locator('#backOverview').click();await filled(p);assert.equal(p.url(),saved);
      await p.locator('#risks').getByRole('link',{name:'DASH-02',exact:true}).click();await filled(p);
      assert.match(p.url(),/\/hoc-vien\/\d+\//);assert.match(await p.locator('h1').innerText(),/DASH-02/);
      assert.equal(await p.locator('#classChart,#learners').count(),0);
      assert.equal(await p.locator('#tasks .lr-row').count(),2);
      await links(p);
      await filter(p,()=>p.locator('#skillChart [data-value=vocabulary]').click());
      await p.locator('#backOverview').click();await filled(p);assert.equal(p.url(),saved);
      await filter(p,()=>p.locator('#resetFilters').click());
      await filter(p,()=>p.locator('#aiChart [data-value=manual]').click());
      assert.equal(await p.locator('#tasks .lr-row').count(),1);assert.equal(await p.locator('#queue .lr-row').count(),1);
      await filter(p,()=>p.locator('#resetFilters').click());
      await filter(p,()=>p.locator('[name=q]').fill('DASH-01'));
      assert.equal(await p.locator('#progress .lr-person').innerText(),'DASH-01');
      await p.reload();await filled(p);assert.equal(await p.locator('[name=q]').inputValue(),'DASH-01');
      await filter(p,()=>p.locator('#resetFilters').click());
    }
    await filter(p,()=>p.locator('.lr-kpi[data-value=review]').click());
    assert.equal(await p.locator('#tasks .lr-row').count(),1);
    await filter(p,()=>p.goBack());assert(!new URL(p.url()).searchParams.has('focus'));
    await filter(p,()=>p.locator('[name=q]').fill('no-matching-title'));
    assert.equal(await p.locator('#tasks .lr-row').count(),0);assert.match(await p.locator('#skillChart').innerText(),/Không có/);
    await filter(p,()=>p.locator('#resetFilters').click());
    await p.screenshot({path:path.join(out,role+'-desktop.png'),fullPage:true});
    for(const width of [1024,390]){
      await p.setViewportSize({width,height:860});
      await checkWorkspace(p);
      const toggle=p.locator('[data-menu-toggle]');
      await toggle.click();
      await settleSidebar(p,await toggle.getAttribute('aria-expanded')==='true');
      await checkWorkspace(p);
      if(width===390){
        if(await toggle.getAttribute('aria-expanded')==='true')await p.keyboard.press('Escape');
        await settleSidebar(p,false);
        const drawer=p.locator('#filterDrawer');
        assert.equal(await drawer.evaluate(el=>el.open),false,'Mobile filters start collapsed');
        await drawer.locator('> summary').click();
        await filter(p,()=>p.locator('[name=skill]').selectOption('listening'));
        await drawer.locator('> summary').click();
        await filter(p,()=>p.getByRole('button',{name:/^Bỏ bộ lọc Kỹ năng:/}).click());
        assert.equal(await drawer.evaluate(el=>el.open),false,'Removing a chip keeps the mobile filters collapsed');
      }
    }
    await p.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
    await p.screenshot({path:path.join(out,role+'-mobile.png'),fullPage:true});
    results.push({role,availableLinks});await ctx.close();
  }
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));
  console.log('PASS: linked dashboard charts, four roles, drill-down, scoped actions and CSV, history, responsive layouts.',JSON.stringify(results));
})().catch(async error=>{
  console.error(error);process.exitCode=1;
  if(lastPage && !lastPage.isClosed()){
    console.error('Page:',lastPage.url(),'Report:',await lastPage.locator('#reportStatus').textContent({timeout:1000}).catch(()=>'unavailable'));
    await lastPage.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});
  }
}).finally(async()=>{
  if(browser)await browser.close();server?.kill();
  if(out!==temp)fs.rmSync(temp,{recursive:true,force:true});
});
