const {chromium}=require('playwright');
const fs=require('fs'),assert=require('node:assert/strict'),{execFileSync,spawn}=require('child_process');
const path=require('path'),os=require('os');
const root=path.resolve(__dirname,'../..'),base='http://127.0.0.1:8765';
const python=process.env.MRBEAN_PYTHON|| (process.platform==='win32'?path.join(root,'.venv','Scripts','python.exe'):path.join(root,'.venv','bin','python'));
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mrbean-e2e-'));
const output=path.resolve(process.env.MRBEAN_QA_OUTPUT||temporary);
fs.mkdirSync(output,{recursive:true});process.chdir(output);
const env={...process.env,DJANGO_DEBUG:'true',OPENAI_API_KEY:'',DJANGO_DB_PATH:path.join(temporary,'test.sqlite3'),DJANGO_MEDIA_ROOT:path.join(temporary,'media')};
execFileSync(python,['manage.py','migrate','--noinput'],{cwd:root,env,stdio:'pipe'});
execFileSync(python,['manage.py','seed_demo','--password','DemoLocal123!'],{cwd:root,env,stdio:'pipe'});
execFileSync('ffmpeg',['-loglevel','error','-f','lavfi','-i','color=c=0x334536:s=640x360:d=3','-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest','-y','sample-reference.mp4'],{stdio:'pipe'});
fs.mkdirSync('screenshots',{recursive:true});
const stamp=Date.now().toString().slice(-7),errors=[],routes=[],results={stamp};
const now=new Date(),start=new Date(now.getTime()-24*3600000).toISOString().slice(0,16),due=new Date(now.getTime()+7*24*3600000).toISOString().slice(0,16);
let server;
process.on('exit',()=>server?.kill());
(async()=>{
const serverLog=fs.openSync('browser-server.log','w');
server=spawn(python,['-u','manage.py','runserver','127.0.0.1:8765','--noreload'],{cwd:root,env,stdio:['ignore',serverLog,serverLog]});
for(let i=0;i<100;i++){try{const r=await fetch(base+'/accounts/login/');if(r.ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
const browser=await chromium.launch({headless:true,executablePath:process.env.MRBEAN_CHROMIUM_PATH||undefined,
 args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'],
});
async function session(username){const ctx=await browser.newContext({viewport:{width:1440,height:1000},permissions:['microphone']});const p=await ctx.newPage();p.on('pageerror',e=>errors.push(username+': '+p.url()+': '+e.message));p.on('response',r=>{if(r.url().startsWith(base)&&r.status()>=400)errors.push(username+': HTTP '+r.status()+' '+r.url());});await p.goto(base+'/accounts/login/');await p.locator('[name=username]').fill(username);await p.locator('[name=password]').fill(username.startsWith('ui_student')?'Learning!8429':'DemoLocal123!');await Promise.all([p.waitForURL(username.startsWith('ui_student')||username==='demo_student'?'**/hoc-tap/':'**/dashboard/'),p.getByRole('button',{name:'Đăng nhập hệ thống',exact:true}).click()]);await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate')?.textContent!=='—');return p;}
async function fill(p,name,value){await p.locator(`[name="${name}"]`).fill(value);}
async function save(p,name='Lưu thay đổi'){await Promise.all([p.waitForURL(url=>!url.pathname.endsWith('/new/')&&!url.pathname.endsWith('/create/')&&!url.pathname.endsWith('/edit/')),p.getByRole('button',{name,exact:true}).click()]);}
const admin=await session('demo_admin');await admin.screenshot({path:'screenshots/admin-desktop.png',fullPage:true});
assert.deepEqual(await admin.locator('.sidebar-menu>li>a>span:first-of-type').allTextContents(),[
 'QUẢN LÝ TÀI KHOẢN','DANH MỤC KHÓA HỌC','QUẢN LÝ LỚP HỌC','KIỂM SOÁT BTVN',
 'NGÂN HÀNG BÀI TẬP','BÀI TẬP ĐÃ GIAO','THÔNG BÁO HỆ THỐNG','BÁO CÁO HỌC TẬP',
 'LIÊN HỆ & PHẢN ÁNH','DJANGO ADMIN']);
results.sidebarOrder='Account, course catalog, classes, homework exemptions, bank, assigned work, notifications, reports, contacts, Django Admin';
await admin.goto(base+'/courses/catalog/new/');await fill(admin,'code','UI-'+stamp);await fill(admin,'name','Khóa học giao diện '+stamp);await admin.locator('[name=course_type]').selectOption('B1');await save(admin);
await admin.getByRole('article').filter({hasText:'UI-'+stamp}).getByRole('link',{name:'Tạo lớp',exact:true}).click();
await fill(admin,'class_code','UI-C'+stamp);await fill(admin,'name','Lớp kiểm thử '+stamp);await admin.locator('[name=teacher]').selectOption(await admin.locator('[name=teacher] option').filter({hasText:'demo_teacher'}).getAttribute('value'));await save(admin,'Lưu lớp học');
const classURL=admin.url();const classID=classURL.match(/classes\/(\d+)/)[1];results.classID=classID;
await admin.goto(base+'/accounts/users/create/');await fill(admin,'username','ui_student'+stamp);await admin.locator('[name=role]').selectOption('student');await fill(admin,'first_name','Học viên kiểm thử');await fill(admin,'student_code','B2026UI'+stamp);await fill(admin,'password','Learning!8429');await fill(admin,'confirm_password','Learning!8429');await save(admin,'Lưu thông tin');
await admin.goto(base+`/courses/classes/${classID}/enroll/`);const studentValue=await admin.locator('[name=student] option').filter({hasText:'ui_student'+stamp}).getAttribute('value');await admin.locator('[name=student]').selectOption(studentValue);await save(admin,'Thêm vào lớp');
assert.equal(await admin.getByRole('link',{name:'Ngừng học',exact:true}).count(),0);
assert.equal(await admin.getByRole('link',{name:'Trạng thái',exact:true}).count(),1);
const teacher=await session('demo_teacher');
async function createLesson(skill,order,title,extras={}){await teacher.goto(base+'/quan-ly/bai-tap/new/');await teacher.locator('[name=skill]').selectOption(skill);await teacher.locator('[name=program]').selectOption('B1');await fill(teacher,'order',String(order));await fill(teacher,'title',title);await fill(teacher,'description','Nội dung dùng kiểm thử giao diện và quy trình.');for(const [key,val]of Object.entries(extras)){if(key==='video_file')await teacher.locator('[name=video_file]').setInputFiles(val);else await fill(teacher,key,val);}await save(teacher,'Lưu buổi');return teacher.url().match(/lesson\/(\d+)/)[1];}
async function assignLesson(lessonID){
 await teacher.goto(base+`/quan-ly/bai-tap/assign/?lesson=${lessonID}&classroom=${classID}`);
 await teacher.locator('[data-assignment-ready=true]').waitFor();
 await fill(teacher,'assigned_at',start);await fill(teacher,'due_at',due);
 if(await teacher.locator('#vocabularyRepetitions').isVisible())await fill(teacher,'repetitions','2');
 else assert(await teacher.locator('[name=repetitions]').isDisabled());
 if(await teacher.locator('#assignmentPreview .assignment-preview-exercise').count())await teacher.screenshot({path:'screenshots/assignment-listening-preview.png',fullPage:true});
 await Promise.all([teacher.waitForURL('**/assigned/*/'),teacher.getByRole('button',{name:'Giao bài cho lớp',exact:true}).click()]);return teacher.url();
}
// Real lesson authoring with four independently added listening exercises.
execFileSync('ffmpeg',['-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=35','-y','sample-listening.mp3'],{stdio:'pipe'});
function writePDF(filename,contents){
 const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids ['+contents.map((_,i)=>(4+i*2)+' 0 R').join(' ')+'] /Count '+contents.length+' >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
 contents.forEach((content,i)=>{objects.push('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents '+(5+i*2)+' 0 R >>','<< /Length '+Buffer.byteLength(content)+' >>\nstream\n'+content+'\nendstream');});
 let pdf='%PDF-1.4\n',offsets=[0];for(let i=0;i<objects.length;i++){offsets.push(Buffer.byteLength(pdf));pdf+=(i+1)+' 0 obj\n'+objects[i]+'\nendobj\n';}const start=Buffer.byteLength(pdf);pdf+='xref\n0 '+(objects.length+1)+'\n0000000000 65535 f \n'+offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')+'trailer\n<< /Size '+(objects.length+1)+' /Root 1 0 R >>\nstartxref\n'+start+'\n%%EOF';fs.writeFileSync(filename,pdf);
}
const pdfLine=(text,x,y)=>'BT /F1 9 Tf '+x+' '+y+' Td ('+text.replace(/[()\\]/g,'\\$&')+') Tj ET';
writePDF('scan-without-text.pdf',['0.9 0.9 0.9 rg 40 60 510 680 re f']);
writePDF('listening-photographs.pdf',[
 '0.94 0.92 0.88 rg 40 60 510 680 re f 0 0 0 rg '+Array.from({length:6},(_,i)=>pdfLine('Photograph '+(i+1),65,710-i*95)).join(' '),
 pdfLine('Listening page two',60,710),
]);
for(const [kind,start,count]of [['part3',32,39],['part4',71,30]]){
 const pages=[];
 for(let offset=0;offset<count;offset+=6){const lines=[];for(let i=offset;i<Math.min(count,offset+6);i++){const slot=i-offset,x=slot<3?35:320,y=780-(slot%3)*225;
  [(kind==='part3'?'Question '+(start+i)+' : ':''+(start+i)+'. ')+'What does the man need to do first?','(A) Change his clothes.','(B) Attach a name tag.','(C) Contact a warehouse supervisor.','(D) Read an employee handbook.'].forEach((line,n)=>lines.push(pdfLine(line,x,y-n*18)));}
  pages.push(lines.join(' '));
 }
 writePDF('listening-'+kind+'.pdf',pages);
}
execFileSync(python,['-c',String.raw`
import zipfile
from html import escape
ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
lines=[line for n in range(71,101) for line in [f'Question {n}: What does the man need to do first?','a: Change his clothes.','b: Attach a name tag.','c: Contact a warehouse supervisor.','d: Read an employee handbook.']]
body=''.join('<w:p><w:r><w:t>'+escape(line)+'</w:t></w:r></w:p>' for line in lines)
with zipfile.ZipFile('listening-part4.docx','w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
 z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
 z.writestr('word/document.xml',f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
`],{stdio:'pipe'});
fs.writeFileSync('listening-key-part2.csv','number,answer\n'+Array.from({length:25},(_,i)=>(i+1)+',B').join('\n'));
await teacher.goto(base+'/quan-ly/bai-tap/');
await teacher.getByRole('link',{name:'Xem buổi và thêm bài',exact:true}).click();
await teacher.getByRole('button',{name:'Tạo buổi tập listening',exact:true}).click();
await teacher.locator('#lessonModal [name=program]').selectOption('B1');
await teacher.locator('#lessonModal [name=order]').fill(stamp);
await teacher.locator('#lessonModal [name=title]').fill('Bài nghe UI '+stamp);
await Promise.all([teacher.waitForURL('**/lesson/*/'),teacher.getByRole('button',{name:'Lưu buổi và thêm bài tập',exact:true}).click()]);
const listening=teacher.url().match(/lesson\/(\d+)/)[1];
await teacher.goto(base+'/quan-ly/bai-tap/skill/listening/');
await teacher.screenshot({path:'screenshots/listening-bank-entry.png',fullPage:true});
await teacher.locator('tbody tr').filter({hasText:'Bài nghe UI '+stamp}).getByRole('link',{name:'Quản lý bài tập',exact:true}).click();
assert.equal(await teacher.locator('[data-add-listening-kind]').count(),4);
await teacher.screenshot({path:'screenshots/listening-type-chooser.png',fullPage:true});
await teacher.setViewportSize({width:390,height:920});
await teacher.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);
assert(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
await teacher.screenshot({path:'screenshots/listening-type-chooser-mobile.png',fullPage:true});
await teacher.setViewportSize({width:1440,height:1000});
assert.match(await teacher.locator('#main-content').innerText(),/Chưa thêm bài nghe/);
await teacher.goto(base+`/quan-ly/bai-tap/assign/?lesson=${listening}&classroom=${classID}`);
await teacher.locator('[data-assignment-ready=false]').waitFor();
assert(await teacher.locator('#assignButton').isDisabled());
assert.match(await teacher.locator('#assignmentPreview').innerText(),/Buổi nghe chưa có bài tập hoặc câu hỏi/);
assert(!(await teacher.locator('#vocabularyRepetitions').isVisible()));
await teacher.screenshot({path:'screenshots/assignment-empty-blocked.png',fullPage:true});
await teacher.setViewportSize({width:390,height:920});
await teacher.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);
assert(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
await teacher.screenshot({path:'screenshots/assignment-empty-mobile.png',fullPage:true});
await teacher.setViewportSize({width:1440,height:1000});
await teacher.getByRole('link',{name:'Quản lý bài tập / bổ sung nội dung',exact:true}).click();
for(const [index,kind,count] of [[1,'part1',6],[2,'part2',25],[3,'part3',39],[4,'part4',30]]){
 await teacher.locator('[data-add-listening-kind='+kind+']').click();
 await teacher.waitForLoadState('domcontentloaded');
 assert.equal(await teacher.locator('[name=kind]').inputValue(),kind);await fill(teacher,'order',String(index));await fill(teacher,'title','Dạng nghe '+index);
 await teacher.waitForFunction(expected=>document.querySelector('[name=question_count]').value===String(expected)&&document.querySelector('[name=question_count]').readOnly,count);assert.equal(await teacher.locator('[name=question_count]').inputValue(),String(count));
 await teacher.locator('[name=audio_file]').setInputFiles('sample-listening.mp3');
 assert(!(await teacher.locator('#questionReview').isVisible()));
 assert.equal(await teacher.getByRole('heading',{name:'3. Câu hỏi và lựa chọn',exact:true}).count(),0);
 if(kind==='part1'||kind==='part2'){assert(!(await teacher.locator('#openQuestionReview').isVisible()));assert(!(await teacher.locator('[data-docx-field]').isVisible()));}
 if(kind==='part1'){await teacher.locator('[name=document_file]').setInputFiles('listening-photographs.pdf');await teacher.waitForFunction(()=>!document.querySelector('#readPDFText').disabled);}
 if(kind==='part3'){await teacher.route('**/listening/extract/',async route=>{const response=await route.fetch(),data=await response.json();data.questions[0].uncertain=true;await route.fulfill({response,json:data});},{times:1});}
 if(kind==='part3'||kind==='part4'){
  await teacher.locator('[name=document_file]').setInputFiles('listening-'+kind+'.pdf');
  await teacher.waitForFunction(expected=>document.querySelector('#pdfImportStatus').textContent.includes('Đã đọc '+expected+'/'+expected),count);
  const questions=JSON.parse(await teacher.locator('[name=question_data]').inputValue());
  assert.equal(questions.length,count);assert.equal(questions[0].number,kind==='part3'?32:71);assert.equal(questions[0].option_b,'Attach a name tag.');
  assert(!(await teacher.locator('#questionReview').isVisible()));
  if(kind==='part4'){
   await teacher.locator('[name=document_file]').setInputFiles('scan-without-text.pdf');
   await teacher.waitForFunction(()=>document.querySelector('#pdfImportStatus').textContent.includes('PDF không có chữ đọc được'));
   assert(JSON.parse(await teacher.locator('[name=question_data]').inputValue()).every(q=>!q.question_text));
   await teacher.locator('#docxQuestions').setInputFiles('listening-part4.docx');
   await teacher.waitForFunction(()=>document.querySelector('#pdfImportStatus').textContent.includes('Đã đọc 30/30 câu từ Word'));
   const wordQuestions=JSON.parse(await teacher.locator('[name=question_data]').inputValue());
   assert.equal(wordQuestions[0].number,71);assert.equal(wordQuestions[29].number,100);assert.equal(wordQuestions[0].option_b,'Attach a name tag.');
   await teacher.locator('[name=document_file]').setInputFiles([]);
   assert.equal(JSON.parse(await teacher.locator('[name=question_data]').inputValue())[0].option_b,'Attach a name tag.');
  }
  if(kind==='part3'){
   assert.match(await teacher.locator('#pdfImportStatus').innerText(),/Có 1 câu cần kiểm tra/);
   await teacher.locator('#openQuestionReview').click();const review=teacher.locator('#questionReview');
   assert(await review.isVisible());assert.equal(await review.locator('#review_question_text').inputValue(),'What does the man need to do first?');
   await review.locator('#review_option_a').fill('Put on a jacket.');await review.getByRole('button',{name:'Đã kiểm tra câu này',exact:true}).click();
   const audit=await new (require('@axe-core/playwright').default)({page:teacher}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
   assert.equal(audit.violations.length,0,'Question correction dialog accessibility: '+JSON.stringify(audit.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))));
   await teacher.screenshot({path:'screenshots/pdf-correction-dialog.png',fullPage:false});
   await review.getByRole('button',{name:'Xong',exact:true}).click();assert(!(await review.isVisible()));
   assert(!/câu cần kiểm tra/.test(await teacher.locator('#pdfImportStatus').innerText()));
   assert.equal(JSON.parse(await teacher.locator('[name=question_data]').inputValue())[0].option_a,'Put on a jacket.');
   await teacher.locator('#openQuestionReview').click();assert.equal(await review.locator('#review_option_a').inputValue(),'Put on a jacket.');
   await review.locator('#review_option_a').press('Enter');assert(!(await review.isVisible()));
   await teacher.locator('#openQuestionReview').click();await teacher.setViewportSize({width:390,height:920});
   assert(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await teacher.screenshot({path:'screenshots/pdf-correction-dialog-mobile.png',fullPage:false});await teacher.keyboard.press('Escape');assert(!(await review.isVisible()));
   assert(await teacher.locator('#openQuestionReview').evaluate(button=>document.activeElement===button));await teacher.setViewportSize({width:1440,height:1000});
  }
 }
 if(kind==='part2'){assert(!(await teacher.locator('[data-pdf-field]').isVisible()));assert(!(await teacher.locator('#questionReview').isVisible()));assert.match(await teacher.locator('#selectedKindMeta').innerText(),/7–31/);}
 if(kind==='part2')await teacher.locator('[name=answer_key_file]').setInputFiles('listening-key-part2.csv');else await fill(teacher,'answer_key',Array.from({length:count},(_,i)=>kind==='part3'?(32+i)+'.B':kind==='part4'?(71+i)+'.B':'B').join(' '));
 if(kind==='part1')await teacher.screenshot({path:'screenshots/listening-bulk-authoring.png',fullPage:true});
 if(kind==='part4'){
  await teacher.screenshot({path:'screenshots/listening-part4-form.png',fullPage:true});
  await teacher.setViewportSize({width:390,height:920});await teacher.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);assert(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await teacher.screenshot({path:'screenshots/listening-part4-form-mobile.png',fullPage:true});
  await teacher.setViewportSize({width:1440,height:1000});
 }
 await Promise.all([teacher.waitForURL('**/lesson/*/'),teacher.getByRole('button',{name:'Lưu bài nghe và đáp án',exact:true}).click()]);
}
assert.equal(await teacher.getByRole('link',{name:'Thêm bài nghe',exact:true}).count(),0);
assert.equal(await teacher.locator('[data-listening-kind]').count(),4);
await teacher.screenshot({path:'screenshots/listening-four-exercises.png',fullPage:true});await assignLesson(listening);
const assignedListeningURL=teacher.url();
await teacher.goto(base+`/quan-ly/bai-tap/assign/?lesson=${listening}&classroom=${classID}`);
await teacher.locator('[data-assignment-ready=false]').waitFor();assert(await teacher.locator('#assignButton').isDisabled());
await teacher.getByRole('link',{name:/Mở lượt giao hiện có/}).click();assert.equal(teacher.url(),assignedListeningURL);
results.assignment='Empty listening blocked with a content-repair link; live preview of four exercises/100 questions; vocabulary repetitions hidden for listening; valid assignment saved; duplicate links to existing assignment';
await teacher.getByRole('link',{name:'Quản lý bài tập của buổi',exact:true}).click();
assert.equal(await teacher.locator('[data-add-listening-kind]').count(),0);
assert.equal(await teacher.getByRole('link',{name:'Tạo bản sao để thêm bài tập',exact:true}).count(),1);
const student=await session('ui_student'+stamp);await student.goto(base+'/hoc-tap/skill/listening/');await student.locator('.space-y-3 > div').filter({hasText:'Bài nghe UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();
const listeningTaskURL=student.url();
const firstAudio=student.locator('#listening-1 audio');
await student.waitForFunction(()=>Number.isFinite(document.querySelector('#listening-1 audio').duration)&&document.querySelector('#listening-1 audio').duration>30);
const audioURL=await firstAudio.getAttribute('src'),rangeResponse=await student.request.get(base+audioURL,{headers:{Range:'bytes=10-19'}});
assert.equal(rangeResponse.status(),206);assert.equal((await rangeResponse.body()).length,10);assert.match(rangeResponse.headers()['content-range'],/^bytes 10-19\//);
const audioTools=student.locator('#listening-1 .audio-tools');
await firstAudio.evaluate(audio=>{audio.currentTime=12;});
await audioTools.getByRole('button',{name:'↶ Lùi 10 giây',exact:true}).click();assert(await firstAudio.evaluate(audio=>audio.currentTime>=1.5&&audio.currentTime<3));
await audioTools.getByRole('button',{name:'Tiến 10 giây ↷',exact:true}).click();assert(await firstAudio.evaluate(audio=>audio.currentTime>=11.5&&audio.currentTime<13));
await audioTools.locator('input').fill('00:20');await audioTools.getByRole('button',{name:'Đi đến',exact:true}).click();
assert(await firstAudio.evaluate(audio=>audio.currentTime>=20&&audio.currentTime<22));await firstAudio.evaluate(audio=>audio.pause());
await audioTools.locator('input').fill('00:15');await audioTools.locator('input').press('Enter');assert(student.url().includes('/tasks/'));await firstAudio.evaluate(audio=>audio.pause());
results.audioSeeking='Authenticated byte ranges, skip backward/forward 10 seconds and jump to mm:ss; Enter keeps the learner in the exercise form';

assert.equal(await student.locator('[data-question]').count(),100);
assert.equal(await student.locator('#listening-2 input[type=radio]').count(),75);
assert.equal(await student.locator('#listening-2 input[type=radio][value=D]').count(),0);
assert.equal(await student.locator('#listening-2 [data-question]').first().getAttribute('data-number'),'7');
assert.equal(await student.locator('#listening-2 [data-question]').last().getAttribute('data-number'),'31');
assert.equal(await student.locator('#listening-2 [data-pdf-url]').count(),0);
assert.equal(await student.locator('#listening-4 [data-question]').first().getAttribute('data-number'),'71');
assert.equal(await student.locator('#listening-4 [data-question]').last().getAttribute('data-number'),'100');
const pdfURL=await student.locator('[data-pdf-url]').first().getAttribute('data-pdf-url');const pdfResponse=await student.request.get(base+pdfURL);assert.equal(pdfResponse.status(),200);assert.match(pdfResponse.headers()['content-type'],/application\/pdf/);assert.equal(pdfResponse.headers()['x-frame-options'],'SAMEORIGIN');
await student.locator('[data-pdf-ready=true]').first().waitFor();
await student.getByRole('button',{name:'Trang PDF tiếp theo',exact:true}).click();
await student.waitForFunction(()=>document.querySelector('[data-pdf-page]').textContent==='Trang 2 / 2');
await student.getByRole('button',{name:'Trang PDF trước',exact:true}).click();
await student.waitForFunction(()=>document.querySelector('[data-pdf-page]').textContent==='Trang 1 / 2');
assert(await student.locator('.pdf-viewport canvas').first().evaluate(canvas=>canvas.width>100&&canvas.height>100));
await student.screenshot({path:'screenshots/source-listening.png',fullPage:true});
async function answerListening({incomplete=false,wrongFirst=false}={}){
 for(const panel of await student.locator('[data-listening-exercise]').all()){
  const order=await panel.getAttribute('data-listening-exercise');await student.locator('[data-listening-tab="'+order+'"]').click();
  const questions=await panel.locator('[data-question]').all();
  for(let i=0;i<questions.length;i++){
   await panel.locator('.listening-question-nav button').nth(i).click();const question=questions[i];
   await question.locator('input[type=radio][value='+((wrongFirst&&order==='1'&&i===0)?'A':'B')+']').check();
   await question.locator('.listening-answer').fill(incomplete&&order==='1'&&i===0?'.':'The answer I heard.');
  }
 }
}
await student.locator('[data-listening-tab="3"]').click();
assert.match(await student.locator('#listening-3 [data-question]:visible').innerText(),/Câu 32[\s\S]*What does the man need to do first[\s\S]*Attach a name tag/);
assert.equal(await student.locator('[data-question]:visible').count(),1);
await student.locator('#listening-3 [data-pdf-toggle]').click();await student.locator('#listening-3 [data-pdf-ready=true]').waitFor();
assert(await student.locator('#listening-3 canvas').evaluate(canvas=>canvas.width>100));await student.locator('#listening-3 [data-pdf-toggle]').click();
await student.screenshot({path:'screenshots/listening-interactive-questions.png',fullPage:true});
await student.setViewportSize({width:390,height:920});await student.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);await student.screenshot({path:'screenshots/listening-interactive-mobile.png',fullPage:true});await student.setViewportSize({width:1440,height:1000});
await answerListening({incomplete:true});
assert.equal(await student.locator('#listeningProgress').innerText(),'Đã trả lời 99/100 câu');
await student.waitForFunction(()=>document.getElementById('draftStatus')?.textContent.startsWith('Đã lưu nháp'));
await student.reload();assert(await student.locator('input[type=radio][value=B]').first().isChecked());assert.equal(await student.locator('.listening-answer').nth(1).inputValue(),'The answer I heard.');
await Promise.all([student.waitForURL('**/results/*/'),student.getByRole('button',{name:'Nộp bài',exact:true}).click()]);
assert.equal(await student.locator('[data-completion-status]').getAttribute('data-completion-status'),'incomplete');assert.equal(await student.locator('[data-final-score]').count(),0);
const partialMetric=await (await student.request.get(base+'/dashboard/metrics/')).json();assert.equal(partialMetric.completed_count,0);
await student.screenshot({path:'screenshots/listening-incomplete-result.png',fullPage:true});
await student.goto(listeningTaskURL);
await answerListening({wrongFirst:true});
await student.setViewportSize({width:390,height:920});assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await student.screenshot({path:'screenshots/listening-mobile.png',fullPage:false});await student.setViewportSize({width:1440,height:1000});
await Promise.all([student.waitForURL('**/results/*/'),student.getByRole('button',{name:'Nộp bài',exact:true}).click()]);
assert.match(await student.locator('body').innerText(),/Đúng 99\/100/);assert.equal(await student.locator('[data-completion-status]').getAttribute('data-completion-status'),'complete');
results.listening='4 manually added exercises, 6/25/39/30 questions; two-column multi-page PDF import 32–70, scan-without-text feedback, DOCX import 71–100 without a PDF; full-text radio choices + short answers; tabs and numbered navigation; CSV and source-numbered keys; draft restored; punctuation-only response is not counted by progress or completion; fully answered attempt with a wrong choice is complete without points';
const vocab=await createLesson('vocabulary',Number(stamp),'Từ vựng UI '+stamp);await teacher.getByRole('button',{name:'Thêm từ vựng',exact:true}).click();await fill(teacher,'order','1');await fill(teacher,'word','Hello');await fill(teacher,'meaning','Xin chào');await teacher.getByRole('button',{name:'Thêm',exact:true}).click();await assignLesson(vocab);
await student.goto(base+'/hoc-tap/skill/vocabulary/');await student.locator('.space-y-3 > div').filter({hasText:'Từ vựng UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();const vocabTaskURL=student.url();await student.screenshot({path:'screenshots/source-vocabulary.png',fullPage:true});await student.getByRole('link',{name:'Cần xin miễn bài này?'}).click();await fill(student,'reason','Xin miễn để kiểm thử quy trình duyệt đúng bài.');await Promise.all([student.waitForURL('**/exemptions/'),student.getByRole('button',{name:'Gửi đơn xin miễn',exact:true}).click()]);
await teacher.goto(base+'/courses/exemptions/');await teacher.locator('tr').filter({hasText:'Từ vựng UI '+stamp}).getByRole('link',{name:'Xét duyệt'}).click();await teacher.locator('[name=action][value=approve]').check();await fill(teacher,'note','Đồng ý miễn bài theo quy định.');await Promise.all([teacher.waitForURL('**/exemptions/'),teacher.getByRole('button',{name:'Xác nhận xử lý',exact:true}).click()]);results.exemption='requested and approved once';
const vocabSubmit=await createLesson('vocabulary',Number(stamp)+1,'Từ nộp UI '+stamp);
await teacher.getByRole('link',{name:'Nhập từ hàng loạt',exact:true}).click();
await fill(teacher,'text','Hello\tinterj\tXin chào\tHello there!\nhello\tinterj\tDòng trùng\t');
await teacher.getByRole('button',{name:'Xem trước danh sách',exact:true}).click();
await teacher.locator('#vocabulary-preview').waitFor();
assert.match(await teacher.locator('#vocabulary-preview').innerText(),/1 từ mới · 1 dòng trùng/);
assert.equal(await teacher.locator('#vocabulary-preview tbody tr').count(),2);
results.vocabularyBulkResponsive=[];
for(const width of [1440,768,390]){
 await teacher.setViewportSize({width,height:950});
 if(width<992)await teacher.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);
 await teacher.evaluate(()=>document.activeElement?.blur());
 assert(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await teacher.screenshot({path:'screenshots/vocabulary-import-'+width+'.png',fullPage:true});
 results.vocabularyBulkResponsive.push(width);
}
await teacher.setViewportSize({width:1440,height:1000});
const vocabBulkAudit=await new (require('@axe-core/playwright').default)({page:teacher}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
assert.equal(vocabBulkAudit.violations.length,0,'Vocabulary import accessibility: '+JSON.stringify(vocabBulkAudit.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))));
await Promise.all([teacher.waitForURL(url=>/\/lesson\/\d+\/$/.test(url.pathname)),teacher.getByRole('button',{name:'Thêm 1 từ vào buổi',exact:true}).click()]);
assert.match(await teacher.locator('#main-content').innerText(),/Hello/);
await assignLesson(vocabSubmit);
await student.goto(base+'/hoc-tap/skill/vocabulary/');await student.locator('.space-y-3 > div').filter({hasText:'Từ nộp UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();
const vocabSubmissionURL=student.url();
assert.equal(await student.locator('#submissionForm textarea, #draftStatus').count(),0);
assert.equal(await student.locator('#submissionForm').getAttribute('data-draft-url'),null);
await student.getByRole('button',{name:'Nộp bài',exact:true}).click();
assert.match(await student.locator('#submissionStatus').innerText(),/ít nhất 1 ảnh/);
execFileSync(python,['-c',`from PIL import Image, ImageDraw
for index in (1,2):
 image=Image.new('RGB',(680,420),'white')
 draw=ImageDraw.Draw(image)
 draw.text((30,30),'Vocabulary homework - page '+str(index),fill='black')
 draw.text((30,100),'Hello    Hello',fill='black')
 image.save('vocabulary-page-'+str(index)+'.png')`],{cwd:output,env,stdio:'pipe'});
const chooserPromise=student.waitForEvent('filechooser');
await student.getByRole('button',{name:'Chọn ảnh bài làm',exact:true}).click();
await (await chooserPromise).setFiles('vocabulary-page-1.png');
assert.equal(await student.locator('#imagePreviews img').count(),1);
await student.locator('#images').setInputFiles('vocabulary-page-2.png');
assert.equal(await student.locator('#imagePreviews img').count(),2);
await student.locator('#imagePreviews button').first().click();
assert.equal(await student.locator('#imagePreviews img').count(),1);
assert.match(await student.locator('#imagePreviews p').innerText(),/1\. vocabulary-page-2\.png/);
await student.locator('#images').setInputFiles('vocabulary-page-1.png');
await student.locator('#images').setInputFiles({name:'not-an-image.txt',mimeType:'text/plain',buffer:Buffer.from('bad')});
assert.match(await student.locator('#submissionStatus').innerText(),/Chỉ nhận ảnh/);
assert.equal(await student.locator('#imagePreviews img').count(),2);
await student.locator('#images').setInputFiles({name:'too-large.png',mimeType:'image/png',buffer:Buffer.alloc(8*1024*1024+1)});
assert.match(await student.locator('#submissionStatus').innerText(),/8 MiB/);
await student.locator('#images').setInputFiles(Array.from({length:4},()=>path.join(output,'vocabulary-page-1.png')));
assert.match(await student.locator('#submissionStatus').innerText(),/Tối đa 5 ảnh/);
assert.equal(await student.locator('#imagePreviews img').count(),2);
const [imageTab]=await Promise.all([student.waitForEvent('popup'),student.locator('#imagePreviews a').first().click()]);
await imageTab.waitForLoadState();assert(imageTab.url().startsWith('blob:'));await imageTab.close();
for(const width of [1440,1024,768,390]){
 await student.setViewportSize({width,height:950});
 if(width<992)await student.waitForFunction(()=>document.getElementById('sidebarMenu').getBoundingClientRect().right<=0);
 assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Image upload overflow at '+width);
 assert(await student.locator('#imagePreviews img').evaluateAll(images=>images.every(img=>img.complete&&img.naturalWidth>0)));
 await student.locator('#submissionStatus').evaluate(el=>{el.textContent='';});
 await student.locator('#vocabularySubmitTitle').scrollIntoViewIfNeeded();
 await student.screenshot({path:'screenshots/vocabulary-image-upload-'+width+'.png',fullPage:false});
}
await student.setViewportSize({width:1440,height:1000});
const imageAudit=await new (require('@axe-core/playwright').default)({page:student}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
assert.equal(imageAudit.violations.length,0,'Image upload accessibility: '+JSON.stringify(imageAudit.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))));
// A failed request keeps the same selection and submission key available for retry.
await student.route('**/ai/submissions/',route=>route.abort('failed'));
await student.getByRole('button',{name:'Nộp bài',exact:true}).click();
await student.waitForFunction(()=>!document.getElementById('submitButton').disabled);
assert.equal(await student.locator('#imagePreviews img').count(),2);
assert(await student.locator('#submissionStatus').innerText());
await student.unroute('**/ai/submissions/');
await Promise.all([student.waitForURL('**/results/*/'),student.getByRole('button',{name:'Nộp bài',exact:true}).click()]);
assert.equal(await student.locator('img[alt^="Ảnh bài từ vựng trang"]').count(),2);
const vocabJobID=student.url().match(/results\/(\d+)/)[1];
execFileSync(python,['manage.py','run_ai_worker','--once'],{cwd:root,env,stdio:'pipe'});
await teacher.goto(base+`/hoc-tap/results/${vocabJobID}/`);assert.equal(await teacher.locator('[name=score]').count(),0);await fill(teacher,'feedback','Đã kiểm tra đủ lượt viết từ vựng.');await teacher.locator('[name=completion_status]').selectOption('complete');await teacher.getByRole('button',{name:'Xác nhận kết quả',exact:true}).click();await teacher.waitForFunction(()=>!document.getElementById('reviewForm'));await student.reload();assert.equal(await student.locator('[data-completion-status]').getAttribute('data-completion-status'),'complete');assert.equal(await student.locator('[data-final-score]').count(),0);results.vocabulary='image-only submission; previews, additive selection and removal; empty/type/size/count validation; responsive and accessible; selection retained after network failure; multipart photos without text → unavailable AI → manual completion confirmation without points';
const speaking=await createLesson('speaking',Number(stamp),'Đọc video UI '+stamp,{video_file:'sample-reference.mp4',reference_transcript:'My hobby is reading.'});await assignLesson(speaking);
await student.goto(base+'/hoc-tap/skill/speaking/');await student.locator('.space-y-3 > div').filter({hasText:'Đọc video UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();assert.equal(await student.locator('input[type=file]').count(),0);assert(!(await student.content()).includes('My hobby is reading.'),'Learner exercise must not contain the reference script');assert.equal(await student.getByText('Lời mẫu cần đọc',{exact:true}).count(),0);await student.getByRole('button',{name:'Bắt đầu ghi âm',exact:true}).click();await student.waitForFunction(()=>document.getElementById('recordStatus').textContent.startsWith('Đang ghi âm'));await new Promise(r=>setTimeout(r,1700));await student.getByRole('button',{name:'Dừng ghi âm',exact:true}).click();await student.waitForFunction(()=>!document.getElementById('submitButton').disabled);await student.screenshot({path:'screenshots/student-recording.png',fullPage:true});await Promise.all([student.waitForURL('**/results/*/'),student.getByRole('button',{name:'Nộp bài',exact:true}).click()]);const jobID=student.url().match(/results\/(\d+)/)[1];results.speakingJobID=jobID;
execFileSync(python,['manage.py','run_ai_worker','--once'],{cwd:root,env,stdio:'pipe'});
await teacher.goto(base+`/hoc-tap/results/${jobID}/`);assert.match(await teacher.locator('#main-content').innerText(),/My hobby is reading\./,'Teacher must retain the reference script');assert.equal(await teacher.locator('[data-grading-state=manual]').count(),1);assert.equal(await teacher.locator('[data-grading-reason]').getAttribute('data-grading-reason'),'provider_not_configured');await teacher.screenshot({path:'screenshots/teacher-ai-fallback.png',fullPage:true});assert.equal(await teacher.locator('#score').count(),0);await teacher.locator('#feedback').fill('Đã kiểm tra bản ghi và lời mẫu. Đã xác nhận hoàn thành.');await teacher.locator('[name=completion_status]').selectOption('complete');await teacher.getByRole('button',{name:'Xác nhận kết quả',exact:true}).click();await teacher.waitForFunction(()=>!document.getElementById('reviewForm'));await student.reload();assert.equal(await student.locator('[data-grading-state],[data-grading-reason]').count(),0);assert(!(await student.content()).includes('My hobby is reading.'),'Learner result must not contain the reference script');assert.equal(await student.getByRole('heading',{name:'Lời mẫu của lần nộp này',exact:true}).count(),0);assert.match(await student.locator('body').innerText(),/Đã xác nhận hoàn thành/);assert.match(await student.locator('[data-final-completion] strong').innerText(),/Hoàn thành/i);assert.equal(await student.locator('[data-final-score]').count(),0);assert(!/AI gợi ý/.test(await student.locator('#main-content').innerText()));results.speaking='microphone-only recording; provider failure → manual → confirmed complete without a score; student sees only the final assessment';
await teacher.goto(base+'/quan-ly/bai-tap/');assert.equal(await teacher.locator('#main-content .grid > div').count(),3);await teacher.screenshot({path:'screenshots/source-bank-overview.png',fullPage:true});await teacher.evaluate(()=>document.fonts.ready);assert(await teacher.evaluate(()=>document.fonts.check('700 16px Montserrat')&&document.fonts.check('400 16px Roboto')));results.sourceFonts='Montserrat and Roboto loaded locally';
await teacher.goto(base+'/quan-ly/bai-tap/skill/speaking/');await teacher.screenshot({path:'screenshots/source-bank-skill.png',fullPage:true});
// Exercise the source modal create/edit/delete controls through the real backend.
await teacher.goto(base+'/quan-ly/bai-tap/skill/vocabulary/');await teacher.getByRole('button',{name:'Tạo buổi tập vocabulary',exact:true}).click();
await teacher.locator('#lessonModal [name=program]').selectOption('B1');await teacher.locator('#lessonModal [name=order]').fill(String(Number(stamp)+5));await teacher.locator('#lessonModal [name=title]').fill('Modal UI '+stamp);
await Promise.all([teacher.waitForURL('**/lesson/*/'),teacher.getByRole('button',{name:'Lưu lại',exact:true}).click()]);
const modalLessonID=teacher.url().match(/lesson\/(\d+)/)[1];
await teacher.goto(base+'/quan-ly/bai-tap/skill/vocabulary/');let modalRow=teacher.locator('tbody tr').filter({hasText:'Modal UI '+stamp});await modalRow.getByRole('button',{name:'Sửa',exact:true}).click();
await teacher.locator('#lessonModal [name=title]').fill('Modal updated UI '+stamp);await teacher.locator('#lessonModal [name=is_active]').uncheck();await Promise.all([teacher.waitForURL('**/lesson/*/'),teacher.getByRole('button',{name:'Lưu lại',exact:true}).click()]);
await teacher.goto(base+'/quan-ly/bai-tap/skill/vocabulary/');modalRow=teacher.locator('tbody tr').filter({hasText:'Modal updated UI '+stamp});assert.match(await modalRow.innerText(),/Ẩn/);await modalRow.getByRole('button',{name:'Xóa',exact:true}).click();await Promise.all([teacher.waitForResponse(r=>r.url().endsWith('/delete/')&&r.request().method()==='POST'),teacher.locator('#deleteModal').getByRole('button',{name:'Xóa',exact:true}).click()]);await teacher.waitForURL('**/bai-tap/');
results.modalWorkflow='source modal create, edit with inactive state, delete through POST passed';
await student.goto(base+'/hoc-tap/');await student.getByRole('link').filter({hasText:'UI-C'+stamp}).click();assert(student.url().endsWith('/hoc-tap/ky-nang/'));await student.screenshot({path:'screenshots/source-learning-home.png',fullPage:true});
await teacher.goto(base+'/dashboard/');await teacher.waitForFunction(()=>document.getElementById('rate').textContent!=='—');await teacher.screenshot({path:'screenshots/teacher-desktop.png',fullPage:true});
await student.goto(base+'/dashboard/');await student.waitForFunction(()=>document.getElementById('rate').textContent!=='—');assert.equal(await student.locator('#rate').innerText(),'100%');await student.screenshot({path:'screenshots/student-desktop.png',fullPage:true});
for(const [role,p]of [['admin',admin],['teacher',teacher],['student',student]]){
 await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');
 assert.equal(await p.locator('.app-sidebar a[href="/ho-tro/hoi-dap/"]').count(),0,role+' has no global knowledge chat in sidebar');
 assert.equal(await p.locator('.app-sidebar details,.app-sidebar summary,.app-sidebar [aria-haspopup]').count(),0,'Flat sidebar '+role);
 assert.equal(await p.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(254, 243, 226)');
 assert.equal(await p.locator('.app-sidebar').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(42, 26, 14)');
 await p.locator('[data-menu-toggle]').click();assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'false');
 const destination=role==='student'?'/hoc-tap/ky-nang/':'/quan-ly/bai-tap/';await p.goto(base+destination);assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'false','Desktop preference persists across shells');
 await p.screenshot({path:'screenshots/palette-'+role+'-closed.png',fullPage:true});
 await p.locator('[data-menu-toggle]').click();assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'true');await p.waitForFunction(()=>Math.abs(document.getElementById('sidebarMenu').getBoundingClientRect().x)<1);await p.screenshot({path:'screenshots/palette-'+role+'-desktop.png',fullPage:true});
 await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');

 assert.equal(await p.locator('#aiScore').count(),0,role+' has no AI score card');assert.equal(await p.locator('.dashboard-stats .stat').count(),role==='admin'?2:3);assert.equal(await p.locator('#score').count(),0);assert.equal(await p.locator('#incompleteCount').count(),role==='admin'?0:1);assert(!/AI gợi ý|duyệt AI/.test(await p.locator('#main-content').innerText()),role+' report only publishes completion assessments');
 const metricResponse=await p.request.get(base+'/dashboard/metrics/');const metricData=await metricResponse.json();assert(!('average_ai_suggestion' in metricData));assert(metricData.history.every(x=>!('suggested_score' in x)&&!('result' in x)));const csv=await p.request.get(base+'/dashboard/export/');assert(!(await csv.text()).split('\n')[0].includes('AI'));
 const links=await p.locator('.app-sidebar a').evaluateAll(as=>[...new Set(as.map(a=>a.getAttribute('href')))]);
 for(const href of links){const response=await p.goto(base+href);assert.equal(response.status(),200,role+' nav '+href);routes.push(role+': '+href);}
 for(const width of [1440,768,390]){await p.setViewportSize({width,height:920});await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');assert(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),role+' horizontal overflow');if(width===390){await p.getByRole('button',{name:'Mở điều hướng',exact:true}).click();assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'true');await p.waitForFunction(()=>Math.abs(document.getElementById('sidebarMenu').getBoundingClientRect().x)<1);await p.screenshot({path:'screenshots/palette-'+role+'-mobile-menu.png',fullPage:false});await p.keyboard.press('Escape');assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'false');await p.screenshot({path:`screenshots/${role}-mobile.png`,fullPage:true});}}
}
const manager=await session('demo_manager');assert.equal(await manager.locator('.dashboard-stats .stat').count(),2);assert.equal(await manager.locator('#score,#aiScore').count(),0);await manager.screenshot({path:'screenshots/manager-desktop-final.png',fullPage:true});await manager.goto(base+`/hoc-tap/results/${jobID}/`);assert.equal(await manager.locator('#reviewForm').count(),0);routes.push('manager: results read only');
// Knowledge questions are attached to published results; AI failure preserves the
// question and handoff/history. Contacts remain a separate human-only channel.
await student.setViewportSize({width:1440,height:1000});await teacher.setViewportSize({width:1440,height:1000});
await student.goto(base+'/dashboard/');
await student.locator('.app-sidebar').getByRole('link',{name:'LIÊN HỆ & PHẢN ÁNH',exact:true}).click();
assert.match(await student.locator('#main-content').innerText(),/Bạn chưa gửi liên hệ nào/);
assert.equal(await student.locator('#main-content a[href="/ho-tro/hoi-dap/"]').count(),0);
await student.screenshot({path:'screenshots/student-contact-inbox-empty.png',fullPage:true});
await student.getByRole('link',{name:'Tạo liên hệ mới',exact:true}).click();
assert.equal(await student.locator('[name=subject],[name=category],[name=target],[name=job],[name=body]').count(),5);
await student.screenshot({path:'screenshots/student-contact-form-desktop.png',fullPage:true});
await student.goto(base+`/hoc-tap/results/${jobID}/`);
await student.getByRole('link',{name:'Hỏi AI về kiến thức bài này',exact:true}).click();
await fill(student,'body','Vì sao câu My hobby is reading dùng reading?');
await Promise.all([student.waitForURL('**/ho-tro/trao-doi/*/'),student.getByRole('button',{name:'Hỏi AI',exact:true}).click()]);
const questionURL=student.url();assert.match(await student.locator('#main-content').innerText(),/Câu hỏi đã được lưu/);
await fill(student,'note','Em chưa hiểu danh động từ, nhờ thầy giải thích thêm.');
await Promise.all([student.waitForResponse(r=>r.url().endsWith('/hoi-giao-vien/')&&r.request().method()==='POST'),student.getByRole('button',{name:'Hỏi giáo viên',exact:true}).click()]);
await student.waitForFunction(()=>document.getElementById('main-content')?.textContent.includes('Chờ phản hồi'));
await teacher.goto(base+'/ho-tro/lien-he/');
await teacher.getByRole('link',{name:'Câu hỏi từ bài tập',exact:true}).click();
await teacher.locator('tr').filter({hasText:'Đọc video UI '+stamp}).getByRole('link',{name:'Mở trao đổi',exact:true}).click();
await fill(teacher,'body','Reading ở đây là danh động từ, ví dụ My hobby is swimming.');
await Promise.all([teacher.waitForResponse(r=>r.url().endsWith('/gui/')&&r.request().method()==='POST'),teacher.getByRole('button',{name:'Gửi phản hồi',exact:true}).click()]);
await teacher.waitForFunction(()=>document.getElementById('main-content')?.textContent.includes('My hobby is swimming'));
await student.goto(questionURL);assert.match(await student.locator('#main-content').innerText(),/My hobby is swimming/);
await student.screenshot({path:'screenshots/student-knowledge-thread.png',fullPage:true});
await Promise.all([student.waitForResponse(r=>r.url().endsWith('/ket-thuc/')&&r.request().method()==='POST'),student.getByRole('button',{name:'Đánh dấu đã giải đáp',exact:true}).click()]);
await student.waitForFunction(()=>document.getElementById('main-content')?.textContent.includes('Mở lại trao đổi'));
await student.getByRole('link',{name:'Liên hệ & phản ánh khác',exact:true}).click();
await fill(student,'subject','Lỗi truy cập video UI '+stamp);await student.locator('[name=category]').selectOption('technical');
const management=await student.locator('[name=target] option').filter({hasText:'Quản lý demo'}).getAttribute('value');await student.locator('[name=target]').selectOption(management);
await fill(student,'body','Em cần quản lý kiểm tra lỗi mở video của buổi học.');
await Promise.all([student.waitForURL('**/ho-tro/trao-doi/*/'),student.getByRole('button',{name:'Gửi liên hệ',exact:true}).click()]);
const contactURL=student.url();await manager.goto(base+'/ho-tro/lien-he/');
await manager.locator('tr').filter({hasText:'Lỗi truy cập video UI '+stamp}).getByRole('link',{name:'Mở trao đổi',exact:true}).click();
await fill(manager,'body','Quản lý đã ghi nhận và sẽ kiểm tra đường dẫn video.');
await Promise.all([manager.waitForResponse(r=>r.url().endsWith('/gui/')&&r.request().method()==='POST'),manager.getByRole('button',{name:'Gửi phản hồi',exact:true}).click()]);
await manager.waitForFunction(()=>document.getElementById('main-content')?.textContent.includes('Quản lý đã ghi nhận'));
await student.goto(contactURL);assert.match(await student.locator('#main-content').innerText(),/Quản lý đã ghi nhận/);
await student.setViewportSize({width:390,height:844});assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await student.screenshot({path:'screenshots/student-contact-mobile.png',fullPage:true});
for(const width of [1440,768,390]){
 await student.setViewportSize({width,height:1000});await student.goto(base+'/ho-tro/lien-he/');
 assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Contact inbox overflow '+width);
 await student.screenshot({path:`screenshots/student-contact-inbox-${width}.png`,fullPage:true});
 await fill(student,'q','Lỗi truy cập video UI '+stamp);await student.locator('[name=status]').selectOption('answered');
 await Promise.all([student.waitForURL(url=>url.pathname==='/ho-tro/lien-he/'&&url.searchParams.get('q')==='Lỗi truy cập video UI '+stamp&&url.searchParams.get('status')==='answered'),student.getByRole('button',{name:'Áp dụng',exact:true}).click()]);
 const filteredContact=student.locator('tbody tr').filter({hasText:'Lỗi truy cập video UI '+stamp});await filteredContact.waitFor({state:'visible'});assert.equal(await filteredContact.count(),1);
 await Promise.all([student.waitForURL(contactURL),student.getByRole('link',{name:'Mở trao đổi',exact:true}).click()]);assert.equal(student.url(),contactURL);
 await student.goto(base+'/ho-tro/lien-he/moi/');assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Contact form overflow '+width);
 if(width===390)await student.screenshot({path:'screenshots/student-contact-form-mobile.png',fullPage:true});
}
await student.goto(base+`/hoc-tap/results/${jobID}/`);await student.getByRole('link',{name:'Hỏi AI về kiến thức bài này',exact:true}).click();assert.equal(student.url(),questionURL);
assert.equal(await student.getByRole('link',{name:'Quay lại kết quả bài tập',exact:true}).getAttribute('href'),`/hoc-tap/results/${jobID}/`);
results.support='No sidebar knowledge chat; result-only AI → teacher tab in contacts → human answer; contact inbox/form/filter/reply at desktop, tablet and mobile';

// Preserve each imported layout while verifying small screens and source navigation.
for(const[p,role,urls]of [[teacher,'teacher',['/quan-ly/bai-tap/','/quan-ly/bai-tap/skill/speaking/','/quan-ly/bai-tap/new/']],[student,'student',['/hoc-tap/','/hoc-tap/ky-nang/','/hoc-tap/skill/listening/',listeningTaskURL.replace(base,'')]]]){
 for(const width of [1440,768,390])for(const url of urls){await p.setViewportSize({width,height:950});await p.goto(base+url);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),role+' source overflow '+width+' '+url);if(width===390){await p.getByRole('button',{name:'Mở điều hướng',exact:true}).click();assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'true');await p.locator('[data-menu-close]').click();assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'false');}if(width===390)await p.screenshot({path:'screenshots/source-'+role+'-'+url.replace(/[^a-z]/g,'-')+'-mobile.png',fullPage:true});}
}
const unassignedListening=await createLesson('listening',Number(stamp)+10,'Đề nghe nháp UI '+stamp);
const listeningDraftURL=`/quan-ly/bai-tap/lesson/${unassignedListening}/`;
const listeningFormURL=`/quan-ly/bai-tap/lesson/${unassignedListening}/listening/new/?kind=part4`;
for(const p of [teacher,admin]){
 for(const width of [1440,768,390]){
  await p.setViewportSize({width,height:950});
  for(const url of [listeningDraftURL,listeningFormURL]){
   await p.goto(base+url);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
 }
 await p.setViewportSize({width:1440,height:1000});await p.goto(base+listeningDraftURL);
 assert.equal(await p.locator('[data-add-listening-kind]').count(),4);
}
await teacher.goto(base+listeningFormURL);await teacher.evaluate(()=>document.fonts.ready);
const authoringStyle=await teacher.evaluate(()=>({body:getComputedStyle(document.body).fontFamily,heading:getComputedStyle(document.querySelector('h1')).fontFamily,background:getComputedStyle(document.body).backgroundColor,button:getComputedStyle(document.querySelector('.listening-button')).backgroundColor}));
assert.match(authoringStyle.body,/Roboto/);assert.match(authoringStyle.heading,/Montserrat/);assert.equal(authoringStyle.background,'rgb(254, 243, 226)');
results.authoringStyle=authoringStyle;
results.authoring='Compact authoring with no inline question editor or 0/N counter; automatic PDF import and bulk keys; optional correction dialog persists edits and reviewed flags; Enter/Escape and mobile keyboard focus; four type cards and fixed 6/25/39/30 counts';
// Delete an unsubmitted class assignment through its confirmation page.
const deleteLessonTitle='Bài giao để xóa UI '+stamp;
const deleteLesson=await createLesson('vocabulary',Number(stamp)+3,deleteLessonTitle);
await teacher.getByRole('link',{name:'Nhập từ hàng loạt',exact:true}).click();
fs.writeFileSync('vocabulary-import.csv','\ufeffword,word_type,meaning,example\nCustomer,n,Khách hàng,A regular customer.\nDepartment,,,\nSign up,,,\n');
await teacher.locator('[name=upload]').setInputFiles('vocabulary-import.csv');
await teacher.getByRole('button',{name:'Xem trước danh sách',exact:true}).click();
await teacher.locator('#vocabulary-preview').waitFor();
assert.match(await teacher.locator('#vocabulary-preview').innerText(),/3 từ mới · 0 dòng trùng/);
await Promise.all([teacher.waitForURL(url=>/\/lesson\/\d+\/$/.test(url.pathname)),teacher.getByRole('button',{name:'Thêm 3 từ vào buổi',exact:true}).click()]);
results.vocabularyBulk='Paste Excel columns or upload UTF-8 CSV; preview before writes; case-insensitive duplicates skipped; optional meaning; assign imported words through existing class workflow';
const deleteAssignmentURL=await assignLesson(deleteLesson);
await teacher.goto(base+'/quan-ly/bai-tap/assigned/');
await teacher.locator('tbody tr').filter({hasText:deleteLessonTitle}).getByRole('link',{name:/Xóa lượt giao/}).click();
const deleteAssignmentConfirmURL=teacher.url();
assert.equal(await teacher.getByRole('button',{name:'Xác nhận xóa lượt giao',exact:true}).count(),1);
await teacher.getByRole('link',{name:'Hủy',exact:true}).click();assert.equal(teacher.url(),deleteAssignmentURL);
await teacher.goto(classURL);
await teacher.locator('tbody tr').filter({hasText:deleteLessonTitle}).getByRole('link',{name:/Xóa lượt giao/}).click();
assert.equal(teacher.url(),deleteAssignmentConfirmURL);
for(const width of [1440,768,390]){
 await teacher.setViewportSize({width,height:950});
 assert(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await teacher.screenshot({path:'screenshots/assignment-delete-'+width+'.png',fullPage:true});
}
await teacher.setViewportSize({width:1440,height:1000});
await Promise.all([teacher.waitForURL('**/assigned/'),teacher.getByRole('button',{name:'Xác nhận xóa lượt giao',exact:true}).click()]);
assert.equal(await teacher.locator('tbody tr').filter({hasText:deleteLessonTitle}).count(),0);
await teacher.goto(base+`/quan-ly/bai-tap/lesson/${deleteLesson}/`);
assert.match(await teacher.locator('#main-content').innerText(),/Customer/);
await student.goto(base+'/hoc-tap/skill/vocabulary/');assert(!(await student.locator('#main-content').innerText()).includes(deleteLessonTitle));
await teacher.goto(base+'/quan-ly/bai-tap/assigned/');
await teacher.locator('tbody tr').filter({hasText:'Từ nộp UI '+stamp}).getByRole('link',{name:/Xóa lượt giao/}).click();
assert.match(await teacher.locator('#main-content').innerText(),/đã có bài nộp/);
assert.equal(await teacher.getByRole('button',{name:'Xác nhận xóa lượt giao',exact:true}).count(),0);
await teacher.screenshot({path:'screenshots/assignment-delete-protected.png',fullPage:true});
results.assignmentDeletion='List, detail and classroom links; cancel and confirm; responsive 390/768/1440; original lesson retained; learner assignment removed; submitted assignment protected';
// Admin can permanently delete an account with conversations and messages.
execFileSync(python,['manage.py','shell','-c',`from accounts.models import CustomUser; from support.models import Conversation, Message; u=CustomUser.objects.create_user(username='delete_user_${stamp}',role='student'); c=Conversation.objects.create(student=u,kind='contact',subject='Liên hệ cần xóa',recipient=CustomUser.objects.get(username='demo_admin'),recipient_role='management'); Message.objects.create(conversation=c,author=u,role='student',body='Tin nhắn của tài khoản kiểm thử')`],{cwd:root,env,stdio:'pipe'});
await admin.goto(base+'/accounts/users/?q=delete_user_'+stamp);
const userDeleteRow=admin.locator('tbody tr').filter({hasText:'delete_user_'+stamp});
assert.equal(await userDeleteRow.getByRole('link',{name:'Khóa',exact:true}).count(),1);
await userDeleteRow.getByRole('link',{name:'Xóa',exact:true}).click();
for(const width of [1440,768,390]){
 await admin.setViewportSize({width,height:950});assert(await admin.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await admin.screenshot({path:'screenshots/user-delete-'+width+'.png',fullPage:true});
}
await admin.setViewportSize({width:1440,height:1000});
await fill(admin,'confirm_username','delete_user_'+stamp);
await Promise.all([admin.waitForURL('**/accounts/users/'),admin.getByRole('button',{name:'Xác nhận xóa vĩnh viễn',exact:true}).click()]);
await admin.goto(base+'/accounts/users/?q=delete_user_'+stamp);
assert.equal(await admin.locator('tbody tr').filter({hasText:'delete_user_'+stamp}).count(),0);
results.userDeletion='Separate Lock/Delete actions; admin permanent deletion with exact username confirmation; related contact/message removed; responsive 390/768/1440';
const vocabularyLayout=await createLesson('vocabulary',Number(stamp)+4,'Từ vựng căn nút '+stamp);
await teacher.getByRole('link',{name:'Nhập từ hàng loạt',exact:true}).click();
await teacher.locator('[name=upload]').setInputFiles(path.join(root,'assignments/testdata/vocabulary_full_entries.csv'));
await teacher.getByRole('button',{name:'Xem trước danh sách',exact:true}).click();
assert.equal(await teacher.locator('#vocabulary-preview tbody tr').count(),10);
await Promise.all([teacher.waitForURL('**/lesson/*/'),teacher.getByRole('button',{name:'Thêm 10 từ vào buổi',exact:true}).click()]);
const vocabularyLayoutURL=teacher.url();
results.responsive=[];
for(const[role,p,urls]of [
 ['admin',admin,['/accounts/users/','/courses/catalog/','/courses/classes/create/','/dashboard/','/accounts/profile/']],
 ['teacher',teacher,['/quan-ly/bai-tap/skill/listening/',listeningFormURL,`/quan-ly/bai-tap/assign/?lesson=${listening}&classroom=${classID}`,'/ho-tro/lien-he/','/dashboard/',vocabularyLayoutURL.replace(base,'')]],
 ['student',student,[listeningTaskURL.replace(base,'')+'#listening-3','/hoc-tap/ky-nang/','/ho-tro/lien-he/moi/','/courses/','/dashboard/']],
]){
 for(const width of [1440,1200,1024,768,390])for(const url of urls){
  await p.setViewportSize({width,height:950});await p.goto(base+url);
  for(const open of width>=992?[true,false]:[false]){
   const toggle=p.locator('[data-menu-toggle]');if((await toggle.getAttribute('aria-expanded')==='true')!==open)await toggle.click();
   await p.waitForFunction(expected=>{const rect=document.getElementById('sidebarMenu').getBoundingClientRect();return expected?Math.abs(rect.x)<1:rect.right<=0;},open);
   await p.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   const layout=await p.evaluate(()=>{const brand=document.querySelector('.topbar-brand').getBoundingClientRect(),actions=document.querySelector('.topbar-actions').getBoundingClientRect();return{width:innerWidth,pageWidth:document.documentElement.scrollWidth,overlap:brand.right>actions.left+1};});
   assert(layout.pageWidth<=layout.width+1,`${role} ${width}px sidebar=${open} overflow ${url}: ${JSON.stringify(layout)}`);
   assert(!layout.overlap,`${role} ${width}px header overlap ${url}`);
   assert.equal(await p.locator('.unified-topbar').count(),1);
   if(role==='admin'&&url==='/accounts/users/'){
    const rows=await p.locator('.user-row-actions').evaluateAll(groups=>groups.map(group=>[...group.querySelectorAll('a')].map(a=>{const r=a.getBoundingClientRect();return {top:r.top,height:r.height};})));
    for(const buttons of rows){assert(new Set(buttons.map(b=>Math.round(b.top))).size<=1,'User actions wrapped');assert(buttons.every(b=>b.height<60),'User action label wrapped');}
    if(width===1024&&open)await p.screenshot({path:'screenshots/users-one-line-actions-1024.png',fullPage:true});
   }
   if(role==='teacher'&&url===vocabularyLayoutURL.replace(base,'')){
    const edits=await p.locator('.lesson-content-actions>a').evaluateAll(as=>as.map(a=>a.getBoundingClientRect().right));
    assert.equal(edits.length,10);assert(Math.max(...edits)-Math.min(...edits)<1,'Vocabulary edit buttons are misaligned');
    if(width===1024&&open)await p.screenshot({path:'screenshots/vocabulary-aligned-actions-1024.png',fullPage:true});
   }
   if(width===1024&&open&&url===listeningFormURL)await p.screenshot({path:'screenshots/listening-form-sidebar-1024.png',fullPage:true});
   if(width===1200&&open&&role==='student'&&url.includes('/tasks/'))await p.screenshot({path:'screenshots/listening-sidebar-1200.png',fullPage:true});
   results.responsive.push({role,width,url,sidebar:open?'open':'closed'});
  }
 }
 await p.setViewportSize({width:1440,height:1000});await p.goto(base+'/dashboard/');
 await p.locator('.topbar-account summary').click();assert(await p.locator('.topbar-account-menu').isVisible());await p.keyboard.press('Escape');assert(!(await p.locator('.topbar-account-menu').isVisible()));
}
const AxeBuilder=require('@axe-core/playwright').default;results.accessibility=[];results.accessibilityMode='prefers-contrast: more';
const anonymousContext=await browser.newContext();const anon=await anonymousContext.newPage();await anon.emulateMedia({contrast:'more'});for(const url of ['/accounts/login/','/login/']){await anon.goto(base+url);await anon.screenshot({path:'screenshots/palette-login-'+(url==='/login/'?'learning':'admin')+'.png',fullPage:true});const anonymousReport=await new AxeBuilder({page:anon}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();results.accessibility.push({role:'anonymous',url,violations:anonymousReport.violations.map(v=>({id:v.id,impact:v.impact}))});}await anonymousContext.close();
for(const[role,p]of [['admin',admin],['teacher',teacher],['student',student]]){
 await p.setViewportSize({width:1440,height:1000});await p.emulateMedia({contrast:'more'});
 const urls=role==='admin'?['/dashboard/','/accounts/users/','/accounts/users/create/','/courses/catalog/','/courses/classes/create/','/accounts/notifications/','/accounts/profile/','/ho-tro/hoi-dap/','/ho-tro/lien-he/']:
 role==='teacher'?['/dashboard/','/quan-ly/bai-tap/','/quan-ly/bai-tap/new/','/quan-ly/bai-tap/assigned/','/quan-ly/bai-tap/assign/','/courses/exemptions/','/quan-ly/bai-tap/skill/listening/','/quan-ly/bai-tap/skill/speaking/',`/quan-ly/bai-tap/lesson/${listening}/`,listeningDraftURL,listeningFormURL,'/ho-tro/hoi-dap/','/ho-tro/lien-he/',questionURL.replace(base,'')]:
 ['/dashboard/','/hoc-tap/','/hoc-tap/ky-nang/','/hoc-tap/skill/listening/','/hoc-tap/skill/speaking/',listeningTaskURL.replace(base,''),vocabTaskURL.replace(base,''),vocabSubmissionURL.replace(base,''),'/courses/',`/courses/classes/${classID}/`,`/hoc-tap/results/${jobID}/`,'/ho-tro/lien-he/','/ho-tro/lien-he/moi/',questionURL.replace(base,''),contactURL.replace(base,'')];
 for(const url of urls){await p.goto(base+url);if(url==='/dashboard/')await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');const report=await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();results.accessibility.push({role,url,violations:report.violations.map(v=>({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)}))});}
 await p.emulateMedia({contrast:'no-preference'});await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');await p.screenshot({path:`screenshots/${role}-desktop-final.png`,fullPage:true});
}
for(const[role,p,urls]of [['admin',admin,['/accounts/users/','/courses/','/dashboard/','/admin/']],['teacher',teacher,['/quan-ly/bai-tap/','/quan-ly/bai-tap/new/']],['student',student,['/hoc-tap/ky-nang/','/ho-tro/lien-he/','/ho-tro/lien-he/moi/']]]){
 await p.setViewportSize({width:1440,height:1000});await p.emulateMedia({contrast:'no-preference'});
 for(const url of urls){await p.goto(base+url);if(url==='/dashboard/')await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');const report=await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();results.accessibility.push({role,url,contrast:'default',violations:report.violations.map(v=>({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)}))});}
}
results.routes=routes;results.errors=errors;fs.writeFileSync('browser-qa-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));console.log('QA output: '+output);await browser.close();server.kill();assert.equal(errors.length,0,'Browser console/HTTP errors');assert.equal(results.accessibility.flatMap(r=>r.violations).length,0,'Accessibility violations');
})().catch(e=>{console.error(e.stack);console.error(JSON.stringify({errors}));process.exit(1)});
