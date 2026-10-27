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
async function session(username){const ctx=await browser.newContext({viewport:{width:1440,height:1000},permissions:['microphone']});const p=await ctx.newPage();p.on('pageerror',e=>errors.push(username+': '+e.message));p.on('response',r=>{if(r.url().startsWith(base)&&r.status()>=400)errors.push(username+': HTTP '+r.status()+' '+r.url());});await p.goto(base+'/accounts/login/');await p.locator('[name=username]').fill(username);await p.locator('[name=password]').fill(username.startsWith('ui_student')?'Learning!8429':'DemoLocal123!');await Promise.all([p.waitForURL(username.startsWith('ui_student')||username==='demo_student'?'**/hoc-tap/':'**/dashboard/'),p.getByRole('button',{name:'Đăng nhập hệ thống',exact:true}).click()]);await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate')?.textContent!=='—');return p;}
async function fill(p,name,value){await p.locator(`[name="${name}"]`).fill(value);}
async function save(p,name='Lưu thay đổi'){await Promise.all([p.waitForURL(url=>!url.pathname.endsWith('/new/')&&!url.pathname.endsWith('/create/')&&!url.pathname.endsWith('/edit/')),p.getByRole('button',{name,exact:true}).click()]);}
const admin=await session('demo_admin');await admin.screenshot({path:'screenshots/admin-desktop.png',fullPage:true});
await admin.goto(base+'/courses/catalog/new/');await fill(admin,'code','UI-'+stamp);await fill(admin,'name','Khóa học giao diện '+stamp);await admin.locator('[name=course_type]').selectOption('B1');await save(admin);
await admin.getByRole('article').filter({hasText:'UI-'+stamp}).getByRole('link',{name:'Tạo lớp',exact:true}).click();
await fill(admin,'class_code','UI-C'+stamp);await fill(admin,'name','Lớp kiểm thử '+stamp);await admin.locator('[name=teacher]').selectOption(await admin.locator('[name=teacher] option').filter({hasText:'demo_teacher'}).getAttribute('value'));await save(admin,'Lưu lớp học');
const classURL=admin.url();const classID=classURL.match(/classes\/(\d+)/)[1];results.classID=classID;
await admin.goto(base+'/accounts/users/create/');await fill(admin,'username','ui_student'+stamp);await admin.locator('[name=role]').selectOption('student');await fill(admin,'first_name','Học viên kiểm thử');await fill(admin,'student_code','B2026UI'+stamp);await fill(admin,'password','Learning!8429');await fill(admin,'confirm_password','Learning!8429');await save(admin,'Lưu thông tin');
await admin.goto(base+`/courses/classes/${classID}/enroll/`);const studentValue=await admin.locator('[name=student] option').filter({hasText:'ui_student'+stamp}).getAttribute('value');await admin.locator('[name=student]').selectOption(studentValue);await save(admin,'Thêm vào lớp');
const teacher=await session('demo_teacher');
async function createLesson(skill,order,title,extras={}){await teacher.goto(base+'/quan-ly/bai-tap/new/');await teacher.locator('[name=skill]').selectOption(skill);await teacher.locator('[name=program]').selectOption('B1');await fill(teacher,'order',String(order));await fill(teacher,'title',title);await fill(teacher,'description','Nội dung dùng kiểm thử giao diện và quy trình.');for(const [key,val]of Object.entries(extras)){if(key==='video_file')await teacher.locator('[name=video_file]').setInputFiles(val);else await fill(teacher,key,val);}await save(teacher,'Lưu buổi');return teacher.url().match(/lesson\/(\d+)/)[1];}
async function assignLesson(lessonID){await teacher.goto(base+`/quan-ly/bai-tap/assign/?lesson=${lessonID}&classroom=${classID}`);await fill(teacher,'assigned_at',start);await fill(teacher,'due_at',due);await fill(teacher,'repetitions','2');await Promise.all([teacher.waitForURL('**/assigned/*/'),teacher.getByRole('button',{name:'Lưu thay đổi',exact:true}).click()]);return teacher.url();}
const listening=await createLesson('listening',Number(stamp),'Bài nghe UI '+stamp);
await teacher.getByRole('button',{name:'Thêm câu hỏi',exact:true}).click();await fill(teacher,'order','1');await fill(teacher,'question_text','Which answer is correct?');await fill(teacher,'option_a','First choice');await fill(teacher,'option_b','Second choice');await teacher.locator('[name=correct_option]').selectOption('B');await teacher.getByRole('button',{name:'Thêm',exact:true}).click();await teacher.waitForURL('**/lesson/*/');await assignLesson(listening);
const student=await session('ui_student'+stamp);await student.goto(base+'/hoc-tap/skill/listening/');await student.locator('.space-y-3 > div').filter({hasText:'Bài nghe UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();
const listeningTaskURL=student.url();await student.screenshot({path:'screenshots/source-listening.png',fullPage:true});await student.waitForFunction(()=>typeof document.getElementById('submissionForm')?.onsubmit==='function');await student.locator('input[type=radio][value=B]').check();await student.waitForFunction(()=>document.getElementById('draftStatus')?.textContent.startsWith('Đã lưu nháp'));
await student.reload();assert(await student.locator('input[type=radio][value=B]').isChecked());await Promise.all([student.waitForURL('**/results/*/'),student.getByRole('button',{name:'Nộp bài',exact:true}).click()]);assert.match(await student.locator('body').innerText(),/Đúng 1\/1/);results.listening='auto-graded 10/10; draft restored';
const vocab=await createLesson('vocabulary',Number(stamp),'Từ vựng UI '+stamp);await teacher.getByRole('button',{name:'Thêm từ vựng',exact:true}).click();await fill(teacher,'order','1');await fill(teacher,'word','Hello');await fill(teacher,'meaning','Xin chào');await teacher.getByRole('button',{name:'Thêm',exact:true}).click();await assignLesson(vocab);
await student.goto(base+'/hoc-tap/skill/vocabulary/');await student.locator('.space-y-3 > div').filter({hasText:'Từ vựng UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();const vocabTaskURL=student.url();await student.screenshot({path:'screenshots/source-vocabulary.png',fullPage:true});await student.getByRole('link',{name:'Cần xin miễn bài này?'}).click();await fill(student,'reason','Xin miễn để kiểm thử quy trình duyệt đúng bài.');await Promise.all([student.waitForURL('**/exemptions/'),student.getByRole('button',{name:'Gửi đơn xin miễn',exact:true}).click()]);
await teacher.goto(base+'/courses/exemptions/');await teacher.locator('tr').filter({hasText:'Từ vựng UI '+stamp}).getByRole('link',{name:'Xét duyệt'}).click();await teacher.locator('[name=action][value=approve]').check();await fill(teacher,'note','Đồng ý miễn bài theo quy định.');await Promise.all([teacher.waitForURL('**/exemptions/'),teacher.getByRole('button',{name:'Xác nhận xử lý',exact:true}).click()]);results.exemption='requested and approved once';
const vocabSubmit=await createLesson('vocabulary',Number(stamp)+1,'Từ nộp UI '+stamp);await teacher.getByRole('button',{name:'Thêm từ vựng',exact:true}).click();await fill(teacher,'order','1');await fill(teacher,'word','Hello');await fill(teacher,'meaning','Xin chào');await teacher.getByRole('button',{name:'Thêm',exact:true}).click();await assignLesson(vocabSubmit);
await student.goto(base+'/hoc-tap/skill/vocabulary/');await student.locator('.space-y-3 > div').filter({hasText:'Từ nộp UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();const vocabSubmissionURL=student.url();await fill(student,'text','Hello Hello');await student.waitForFunction(()=>document.getElementById('draftStatus').textContent.startsWith('Đã lưu nháp'));await student.screenshot({path:'screenshots/source-vocabulary-submit.png',fullPage:true});await Promise.all([student.waitForURL('**/results/*/'),student.getByRole('button',{name:'Nộp bài',exact:true}).click()]);const vocabJobID=student.url().match(/results\/(\d+)/)[1];
execFileSync(python,['manage.py','run_ai_worker','--once'],{cwd:root,env,stdio:'pipe'});
await teacher.goto(base+`/hoc-tap/results/${vocabJobID}/`);await fill(teacher,'score','8.5');await fill(teacher,'feedback','Đã kiểm tra đủ lượt viết từ vựng.');await teacher.getByRole('button',{name:'Xác nhận điểm',exact:true}).click();await teacher.waitForFunction(()=>!document.getElementById('reviewForm'));await student.reload();assert.equal(await student.locator('[data-final-score] strong').innerText().then(t=>t.replace(',','.')),'8.5');results.vocabulary='text draft/submission → unavailable AI → manual confirmation 8.5';
const speaking=await createLesson('speaking',Number(stamp),'Đọc video UI '+stamp,{video_file:'sample-reference.mp4',reference_transcript:'My hobby is reading.'});await assignLesson(speaking);
await student.goto(base+'/hoc-tap/skill/speaking/');await student.locator('.space-y-3 > div').filter({hasText:'Đọc video UI '+stamp}).getByRole('link',{name:'Làm bài',exact:true}).click();assert.equal(await student.locator('input[type=file]').count(),0);await student.getByRole('button',{name:'Bắt đầu ghi âm',exact:true}).click();await student.waitForFunction(()=>document.getElementById('recordStatus').textContent.startsWith('Đang ghi âm'));await new Promise(r=>setTimeout(r,1700));await student.getByRole('button',{name:'Dừng ghi âm',exact:true}).click();await student.waitForFunction(()=>!document.getElementById('submitButton').disabled);await student.screenshot({path:'screenshots/student-recording.png',fullPage:true});await Promise.all([student.waitForURL('**/results/*/'),student.getByRole('button',{name:'Nộp bài',exact:true}).click()]);const jobID=student.url().match(/results\/(\d+)/)[1];results.speakingJobID=jobID;
execFileSync(python,['manage.py','run_ai_worker','--once'],{cwd:root,env,stdio:'pipe'});
await teacher.goto(base+`/hoc-tap/results/${jobID}/`);await teacher.locator('#score').fill('7.5');await teacher.locator('#feedback').fill('Đã kiểm tra bản ghi và lời mẫu. Điểm chấm thủ công.');await teacher.getByRole('button',{name:'Xác nhận điểm',exact:true}).click();await teacher.waitForFunction(()=>!document.getElementById('reviewForm'));await student.reload();assert.match(await student.locator('body').innerText(),/Điểm chấm thủ công/);assert.equal(await student.locator('[data-final-score] strong').innerText().then(t=>t.replace(',','.')),'7.5');assert(!/AI gợi ý/.test(await student.locator('#main-content').innerText()));results.speaking='microphone-only recording; provider failure → manual → confirmed 7.5; student sees only final grade';
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
 assert.equal(await p.locator('#aiScore').count(),0,role+' has no AI score card');assert.equal(await p.locator('.dashboard-stats .stat').count(),role==='admin'?2:3);assert.equal(await p.locator('#score').count(),role==='admin'?0:1);assert(!/AI gợi ý|duyệt AI/.test(await p.locator('#main-content').innerText()),role+' report only publishes final scores');
 const metricResponse=await p.request.get(base+'/dashboard/metrics/');const metricData=await metricResponse.json();assert(!('average_ai_suggestion' in metricData));assert(metricData.history.every(x=>!('suggested_score' in x)&&!('result' in x)));const csv=await p.request.get(base+'/dashboard/export/');assert(!(await csv.text()).split('\n')[0].includes('AI'));
 const links=await p.locator('.app-sidebar a').evaluateAll(as=>[...new Set(as.map(a=>a.getAttribute('href')))]);
 for(const href of links){const response=await p.goto(base+href);assert.equal(response.status(),200,role+' nav '+href);routes.push(role+': '+href);}
 for(const width of [1440,768,390]){await p.setViewportSize({width,height:920});await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');assert(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),role+' horizontal overflow');if(width===390){await p.getByRole('button',{name:'Mở điều hướng',exact:true}).click();assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'true');await p.keyboard.press('Escape');assert.equal(await p.locator('[data-menu-toggle]').getAttribute('aria-expanded'),'false');await p.screenshot({path:`screenshots/${role}-mobile.png`,fullPage:true});}}
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
await student.waitForFunction(()=>document.getElementById('main-content').textContent.includes('Chờ phản hồi'));
await teacher.goto(base+'/ho-tro/lien-he/');
await teacher.getByRole('link',{name:'Câu hỏi từ bài tập',exact:true}).click();
await teacher.locator('tr').filter({hasText:'Đọc video UI '+stamp}).getByRole('link',{name:'Mở trao đổi',exact:true}).click();
await fill(teacher,'body','Reading ở đây là danh động từ, ví dụ My hobby is swimming.');
await Promise.all([teacher.waitForResponse(r=>r.url().endsWith('/gui/')&&r.request().method()==='POST'),teacher.getByRole('button',{name:'Gửi phản hồi',exact:true}).click()]);
await teacher.waitForFunction(()=>document.getElementById('main-content').textContent.includes('My hobby is swimming'));
await student.goto(questionURL);assert.match(await student.locator('#main-content').innerText(),/My hobby is swimming/);
await student.screenshot({path:'screenshots/student-knowledge-thread.png',fullPage:true});
await Promise.all([student.waitForResponse(r=>r.url().endsWith('/ket-thuc/')&&r.request().method()==='POST'),student.getByRole('button',{name:'Đánh dấu đã giải đáp',exact:true}).click()]);
await student.waitForFunction(()=>document.getElementById('main-content').textContent.includes('Mở lại trao đổi'));
await student.getByRole('link',{name:'Liên hệ & phản ánh khác',exact:true}).click();
await fill(student,'subject','Lỗi truy cập video UI '+stamp);await student.locator('[name=category]').selectOption('technical');
const management=await student.locator('[name=target] option').filter({hasText:'Quản lý demo'}).getAttribute('value');await student.locator('[name=target]').selectOption(management);
await fill(student,'body','Em cần quản lý kiểm tra lỗi mở video của buổi học.');
await Promise.all([student.waitForURL('**/ho-tro/trao-doi/*/'),student.getByRole('button',{name:'Gửi liên hệ',exact:true}).click()]);
const contactURL=student.url();await manager.goto(base+'/ho-tro/lien-he/');
await manager.locator('tr').filter({hasText:'Lỗi truy cập video UI '+stamp}).getByRole('link',{name:'Mở trao đổi',exact:true}).click();
await fill(manager,'body','Quản lý đã ghi nhận và sẽ kiểm tra đường dẫn video.');
await Promise.all([manager.waitForResponse(r=>r.url().endsWith('/gui/')&&r.request().method()==='POST'),manager.getByRole('button',{name:'Gửi phản hồi',exact:true}).click()]);
await manager.waitForFunction(()=>document.getElementById('main-content').textContent.includes('Quản lý đã ghi nhận'));
await student.goto(contactURL);assert.match(await student.locator('#main-content').innerText(),/Quản lý đã ghi nhận/);
await student.setViewportSize({width:390,height:844});assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await student.screenshot({path:'screenshots/student-contact-mobile.png',fullPage:true});
for(const width of [1440,768,390]){
 await student.setViewportSize({width,height:1000});await student.goto(base+'/ho-tro/lien-he/');
 assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Contact inbox overflow '+width);
 await student.screenshot({path:`screenshots/student-contact-inbox-${width}.png`,fullPage:true});
 await fill(student,'q','Lỗi truy cập video UI '+stamp);await student.locator('[name=status]').selectOption('answered');await student.getByRole('button',{name:'Áp dụng',exact:true}).click();
 assert.equal(await student.locator('tbody tr').filter({hasText:'Lỗi truy cập video UI '+stamp}).count(),1);
 await student.getByRole('link',{name:'Mở trao đổi',exact:true}).click();assert.equal(student.url(),contactURL);
 await student.goto(base+'/ho-tro/lien-he/moi/');assert(await student.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Contact form overflow '+width);
 if(width===390)await student.screenshot({path:'screenshots/student-contact-form-mobile.png',fullPage:true});
}
await student.goto(base+`/hoc-tap/results/${jobID}/`);await student.getByRole('link',{name:'Hỏi AI về kiến thức bài này',exact:true}).click();assert.equal(student.url(),questionURL);
assert.equal(await student.getByRole('link',{name:'Quay lại kết quả bài tập',exact:true}).getAttribute('href'),`/hoc-tap/results/${jobID}/`);
results.support='No sidebar knowledge chat; result-only AI → teacher tab in contacts → human answer; contact inbox/form/filter/reply at desktop, tablet and mobile';

// Preserve each imported layout while verifying small screens and source navigation.
for(const[p,role,urls]of [[teacher,'teacher',['/quan-ly/bai-tap/','/quan-ly/bai-tap/skill/speaking/','/quan-ly/bai-tap/new/']],[student,'student',['/hoc-tap/','/hoc-tap/ky-nang/','/hoc-tap/skill/listening/',listeningTaskURL.replace(base,'')]]]){
 for(const width of [1440,768,390])for(const url of urls){await p.setViewportSize({width,height:950});await p.goto(base+url);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),role+' source overflow '+width+' '+url);if(width===390&&role==='teacher'){await p.getByRole('button',{name:'Điều hướng quản lý',exact:false}).click();assert.equal(await p.locator('#sourceNavToggle').getAttribute('aria-expanded'),'true');await p.keyboard.press('Escape');assert.equal(await p.locator('#sourceNavToggle').getAttribute('aria-expanded'),'false');}if(width===390)await p.screenshot({path:'screenshots/source-'+role+'-'+url.replace(/[^a-z]/g,'-')+'-mobile.png',fullPage:true});}
}
const AxeBuilder=require('@axe-core/playwright').default;results.accessibility=[];results.accessibilityMode='prefers-contrast: more';
const anonymousContext=await browser.newContext();const anon=await anonymousContext.newPage();await anon.emulateMedia({contrast:'more'});for(const url of ['/accounts/login/','/login/']){await anon.goto(base+url);const anonymousReport=await new AxeBuilder({page:anon}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();results.accessibility.push({role:'anonymous',url,violations:anonymousReport.violations.map(v=>({id:v.id,impact:v.impact}))});}await anonymousContext.close();
for(const[role,p]of [['admin',admin],['teacher',teacher],['student',student]]){
 await p.setViewportSize({width:1440,height:1000});await p.emulateMedia({contrast:'more'});
 const urls=role==='admin'?['/dashboard/','/accounts/users/','/accounts/users/create/','/courses/catalog/','/courses/classes/create/','/accounts/notifications/','/accounts/profile/','/ho-tro/hoi-dap/','/ho-tro/lien-he/']:
 role==='teacher'?['/dashboard/','/quan-ly/bai-tap/','/quan-ly/bai-tap/new/','/quan-ly/bai-tap/assigned/','/quan-ly/bai-tap/assign/','/courses/exemptions/','/quan-ly/bai-tap/skill/listening/','/quan-ly/bai-tap/skill/speaking/',`/quan-ly/bai-tap/lesson/${listening}/`,'/ho-tro/hoi-dap/','/ho-tro/lien-he/',questionURL.replace(base,'')]:
 ['/dashboard/','/hoc-tap/','/hoc-tap/ky-nang/','/hoc-tap/skill/listening/','/hoc-tap/skill/speaking/',listeningTaskURL.replace(base,''),vocabTaskURL.replace(base,''),vocabSubmissionURL.replace(base,''),'/courses/',`/courses/classes/${classID}/`,`/hoc-tap/results/${jobID}/`,'/ho-tro/lien-he/','/ho-tro/lien-he/moi/',questionURL.replace(base,''),contactURL.replace(base,'')];
 for(const url of urls){await p.goto(base+url);if(url==='/dashboard/')await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');const report=await new AxeBuilder({page:p}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();results.accessibility.push({role,url,violations:report.violations.map(v=>({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)}))});}
 await p.emulateMedia({contrast:'no-preference'});await p.goto(base+'/dashboard/');await p.waitForFunction(()=>document.getElementById('rate').textContent!=='—');await p.screenshot({path:`screenshots/${role}-desktop-final.png`,fullPage:true});
}
results.routes=routes;results.errors=errors;fs.writeFileSync('browser-qa-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));console.log('QA output: '+output);await browser.close();server.kill();assert.equal(errors.length,0,'Browser console/HTTP errors');assert.equal(results.accessibility.flatMap(r=>r.violations).length,0,'Accessibility violations');
})().catch(e=>{console.error(e.stack);console.error(JSON.stringify({errors}));process.exit(1)});
