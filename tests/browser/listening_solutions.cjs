'use strict';
const {chromium}=require('playwright'),AxeBuilder=require('@axe-core/playwright').default;
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('node:assert/strict');
const {execFileSync,spawn}=require('child_process');
const root=path.resolve(__dirname,'../..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mrbean-solutions-'));
const output=process.env.MRBEAN_QA_OUTPUT||temporary;fs.mkdirSync(output,{recursive:true});
const python=process.env.MRBEAN_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const env={...process.env,DJANGO_DEBUG:'true',OPENAI_API_KEY:'',AI_LOCAL_ENABLED:'false',
 DJANGO_DB_PATH:path.join(temporary,'test.sqlite3'),DJANGO_MEDIA_ROOT:path.join(temporary,'media'),SOLUTIONS_BROWSER_DIR:temporary};
const base='http://127.0.0.1:8769';let server,browser;
(async()=>{
 for(const args of [['migrate','--noinput'],['seed_demo','--password','DemoLocal123!']])execFileSync(python,['manage.py',...args],{cwd:root,env,stdio:'pipe'});
 execFileSync('ffmpeg',['-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=3','-y',path.join(temporary,'audio.mp3')],{stdio:'pipe'});
 const fixture=JSON.parse(execFileSync(python,['manage.py','shell','-c',String.raw`
import os,json
from pathlib import Path
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import CustomUser
from assignments.models import Lesson
from assignments.forms import ListeningExerciseForm
from assignments.services import save_listening_exercise
from assignments.test_listening_solutions import bundle_for, solution_word
from dashboard.models import LearningTask
folder=Path(os.environ['SOLUTIONS_BROWSER_DIR'])
teacher=CustomUser.objects.get(username='demo_teacher')
lesson=Lesson.objects.create(skill='listening',program='B1',order=9876,title='Workshop listening solutions',created_by=teacher)
for order,kind in [(1,'part1'),(2,'part2'),(4,'part4')]:
 files={'audio_file':SimpleUploadedFile('audio.mp3',(folder/'audio.mp3').read_bytes())}
 if kind=='part1':files['document_file']=SimpleUploadedFile('photos.pdf',b'%PDF-1.4\n%%EOF')
 form=ListeningExerciseForm({'order':order,'kind':kind,'solution_data':json.dumps(bundle_for(kind))},files,lesson=lesson)
 assert form.is_valid(),form.errors
 save_listening_exercise(actor=teacher,form=form)
(folder/'solutions-part3.docx').write_bytes(solution_word('part3').read())
(folder/'invalid.docx').write_bytes(b'invalid zip')
classroom=LearningTask.objects.filter(learner__username='demo_student',assignment__isnull=False).first().assignment.classroom
print(json.dumps({'lesson':lesson.pk,'classroom':classroom.pk}))
`],{cwd:root,env,encoding:'utf8'}).trim().split('\n').at(-1));
 const log=fs.openSync(path.join(output,'server.log'),'w');
 server=spawn(python,['manage.py','runserver','127.0.0.1:8769','--noreload'],{cwd:root,env,stdio:['ignore',log,log]});
 for(let i=0;i<100;i++){try{if((await fetch(base+'/accounts/login/')).ok)break;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
 browser=await chromium.launch({headless:true,executablePath:process.env.MRBEAN_CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 const errors=[],audits=[];
 async function session(username){
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base+'/accounts/login/');await page.locator('[name=username]').fill(username);await page.locator('[name=password]').fill('DemoLocal123!');
  await Promise.all([page.waitForURL(username==='demo_student'?'**/hoc-tap/':'**/dashboard/'),page.getByRole('button',{name:'Đăng nhập hệ thống',exact:true}).click()]);return page;
 }
 async function inspect(page,name){
  for(const width of [1440,1024,768,390]){
   await page.setViewportSize({width,height:1000});
   if(width<992)await page.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' overflow '+width);
   const audit=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
   assert.equal(audit.violations.length,0,JSON.stringify({name,width,errors:audit.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))}));
   audits.push({name,width,violations:0});await page.screenshot({path:path.join(output,`${name}-${width}.png`)});
  }
  await page.setViewportSize({width:1440,height:1000});
 }
 const teacher=await session('demo_teacher');
 await teacher.goto(base+`/quan-ly/bai-tap/lesson/${fixture.lesson}/listening/new/?kind=part3`);
 await teacher.locator('[name=order]').fill('3');await teacher.locator('[name=title]').fill('Workshop dialogue');
 await teacher.locator('[name=audio_file]').setInputFiles(path.join(temporary,'audio.mp3'));
 await teacher.locator('[name=solutions_file]').setInputFiles(path.join(temporary,'solutions-part3.docx'));
 await teacher.waitForFunction(()=>document.getElementById('solutionsStatus').textContent.includes('Đã đọc 39 lời giải'));
 assert.equal(await teacher.locator('.solution-question-editor').count(),3);
 assert.equal(await teacher.locator('.solution-passage-editor').count(),1);
 assert.equal(await teacher.locator('#solutionsNav button').count(),13);
 assert.equal(await teacher.locator('[name=solutions_previewed]').inputValue(),'True');
 await teacher.locator('#solution_32_explanation').fill('BROWSER_EDIT: The guide confirms the workshop begins after lunch.');
 await teacher.locator('#solution_32_option_c').fill('Updated workshop choice C.');
 await teacher.getByRole('button',{name:'Xem lời giải câu 35–37',exact:true}).click();
 await teacher.getByRole('button',{name:'Xem lời giải câu 32–34',exact:true}).click();
 assert.match(await teacher.locator('#solution_32_explanation').inputValue(),/^BROWSER_EDIT/);
 assert.equal(JSON.parse(await teacher.locator('[name=question_data]').inputValue())[0].option_c,'Updated workshop choice C.');
 const download=await teacher.request.get(base+await teacher.locator('#downloadSolutionsTemplate').getAttribute('href'));
 assert.equal(download.status(),200);assert.match(download.headers()['content-type'],/wordprocessingml/);
 await teacher.locator('#solutionsReview').scrollIntoViewIfNeeded();await inspect(teacher,'word-authoring');
 await Promise.all([teacher.waitForURL('**/lesson/*/'),teacher.getByRole('button',{name:'Lưu bài nghe và đáp án',exact:true}).click()]);
 const task=execFileSync(python,['manage.py','shell','-c',String.raw`
from django.utils import timezone
from datetime import timedelta
from assignments.models import Lesson
from assignments.services import assign_to_class
from courses.models import ClassRoom
from accounts.models import CustomUser
lesson=Lesson.objects.get(pk=`+fixture.lesson+String.raw`)
assignment=assign_to_class(actor=CustomUser.objects.get(username='demo_teacher'),lesson=lesson,
 classroom=ClassRoom.objects.get(pk=`+fixture.classroom+String.raw`),assigned_at=timezone.now()-timedelta(days=1),due_at=timezone.now()+timedelta(days=1),requires_previous=False)
print(assignment.tasks.get(learner__username='demo_student').pk)
`],{cwd:root,env,encoding:'utf8'}).trim().split('\n').at(-1);
 const student=await session('demo_student');
 await student.goto(base+`/hoc-tap/tasks/${task}/#listening-2`);
 assert(!(await student.content()).includes('PRIVATE_EXPLANATION'));
 assert(!(await student.content()).includes('PRIVATE_PASSAGE'));
 assert(!(await student.content()).includes('What is announced in question 7?'));
 assert.equal(await student.getByRole('link',{name:'Hỏi AI',exact:true}).count(),0);
 const csrf=await student.locator('[name=csrfmiddlewaretoken]').first().inputValue();
 const questionIDs=await student.locator('[data-question]').evaluateAll(nodes=>nodes.map(n=>Number(n.querySelector('input[type=radio]').name.slice(2))));
 const answers=Object.fromEntries(questionIDs.map(id=>[String(id),{chosen:'B',short_answer:'The guide confirms the workshop time.'}]));
 const submission=await student.request.post(base+await student.locator('#submissionForm').getAttribute('action'),{headers:{'X-CSRFToken':csrf},multipart:{task_id:String(task),submission_key:'solutions-browser-attempt',reference_version:await student.locator('[name=reference_version]').inputValue(),answers:JSON.stringify(answers)}});
 assert.equal(submission.status(),201,await submission.text());const submitted=await submission.json();
 await student.goto(base+`/hoc-tap/results/${submitted.id}/`);
 await student.getByRole('link',{name:'Đáp án và giải thích',exact:true}).click();
 assert.match(await student.locator('.solution-explanation').innerText(),/PRIVATE_EXPLANATION_1/);
 await student.getByRole('link',{name:'Bài 2 · Câu 7',exact:true}).click();
 assert.match(await student.locator('.listening-question-text').innerText(),/What is announced in question 7/);
 await inspect(student,'part2-review');
 await student.getByRole('link',{name:'Bài 3 · Câu 32–34',exact:true}).click();
 assert.equal(await student.locator('.solution-review-question').count(),3);
 assert.equal(await student.locator('.solution-shared-passage').count(),1);
 assert.equal((await student.locator('main').innerText()).match(/PRIVATE_PASSAGE_32/g).length,1);
 assert.match(await student.locator('.solution-explanation').first().innerText(),/^Giải thích đáp án B\s+BROWSER_EDIT/);
 assert.match(await student.locator('.solution-review-question').first().innerText(),/Updated workshop choice C/);
 await inspect(student,'shared-dialogue-review');
 await student.getByRole('link',{name:'Hỏi AI về câu 33',exact:true}).click();
 assert.match(await student.locator('[name=body]').inputValue(),/câu 33 chọn B/);
 await inspect(student,'focused-ai-question');
 await student.locator('[name=body]').fill('Vì sao không chọn A ở câu 33?');
 await Promise.all([student.waitForURL('**/trao-doi/*/'),student.getByRole('button',{name:'Hỏi AI',exact:true}).click()]);
 assert.match(await student.locator('main').innerText(),/Câu hỏi đã được lưu/);
 assert.match(await student.locator('.support-message-body').first().innerText(),/Vì sao không chọn A ở câu 33/);
 await inspect(student,'focused-ai-conversation');
 await student.getByRole('link',{name:'Quay lại lời giải',exact:true}).click();
 await student.locator('.solution-review-question').first().waitFor();
 assert.equal(await student.locator('.solution-review-question').count(),3);
 await student.getByRole('link',{name:'Bài 4 · Câu 71–73',exact:true}).click();
 await student.locator('.solution-review-question').first().waitFor();
 assert.equal(await student.locator('.solution-review-question').count(),3);
 assert.match(await student.locator('.solution-shared-passage').innerText(),/Đoạn nói/);
 assert.equal(errors.length,0,JSON.stringify(errors));
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,wordPreviewAndEdits:true,answerPrivacy:true,sharedGroups:true,focusedAI:true,audits,browserErrors:errors},null,2));
 console.log(JSON.stringify({passed:true,audits:audits.length,browserErrors:errors}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
