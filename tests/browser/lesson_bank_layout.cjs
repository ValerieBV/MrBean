'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync, spawn} = require('node:child_process');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '../..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'mrbean-lesson-layout-'));
const output = path.resolve(process.env.MRBEAN_QA_OUTPUT || temporary);
const python = process.env.MRBEAN_PYTHON || (process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe') : path.join(root, '.venv', 'bin', 'python'));
const base = 'http://127.0.0.1:8773';
const env = {...process.env, DJANGO_DEBUG:'true', OPENAI_API_KEY:'', AI_LOCAL_ENABLED:'false',
    DJANGO_DB_PATH:path.join(temporary, 'test.sqlite3'), DJANGO_MEDIA_ROOT:path.join(temporary, 'media')};
const results = [], errors = [];
let server, browser, page;
fs.mkdirSync(output, {recursive:true});
process.on('exit', () => server?.kill());

async function sidebar(open) {
    const toggle = page.locator('[data-menu-toggle]');
    if ((await toggle.getAttribute('aria-expanded') === 'true') !== open) {
        if (open) await toggle.click();
        else await page.locator('#sidebarMenu [data-menu-close]').click();
    }
    await page.waitForFunction(expected => {
        const rect = document.getElementById('sidebarMenu').getBoundingClientRect();
        return expected ? Math.abs(rect.x) < 1 : rect.right <= 0;
    }, open);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

(async () => {
    execFileSync(python, ['manage.py', 'migrate', '--noinput'], {cwd:root, env, stdio:'pipe'});
    execFileSync(python, ['manage.py', 'seed_demo', '--password', 'DemoLocal123!'], {cwd:root, env, stdio:'pipe'});
    execFileSync(python, ['manage.py', 'shell', '-c', String.raw`
from accounts.models import CustomUser
from assignments.models import Lesson
teacher=CustomUser.objects.get(username='demo_teacher')
for skill in ('listening', 'speaking', 'vocabulary'):
    Lesson.objects.create(skill=skill, program='B1', order=99,
        title='Buổi có tên dài để kiểm tra cột tên buổi và thanh bên khi thu hẹp màn hình', created_by=teacher)
`], {cwd:root, env, stdio:'pipe'});
    const log = fs.openSync(path.join(output, 'server.log'), 'w');
    server = spawn(python, ['manage.py', 'runserver', '127.0.0.1:8773', '--noreload'],
        {cwd:root, env, stdio:['ignore', log, log]});
    let ready = false;
    for (let attempt=0; attempt<100; attempt++) {
        try {if ((await fetch(base+'/accounts/login/')).ok) {ready=true;break;}} catch {}
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(ready, 'Django did not start');
    browser = await chromium.launch({headless:true, executablePath:process.env.MRBEAN_CHROMIUM_PATH,
        args:['--no-sandbox', '--disable-dev-shm-usage']});
    for (const username of ['demo_admin', 'demo_teacher']) {
        const context = await browser.newContext({viewport:{width:1440,height:1000}});
        page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        page.on('response', response => {
            if (response.url().startsWith(base) && response.status() >= 400)
                errors.push(response.status()+' '+response.url());
        });
        await page.goto(base+'/accounts/login/');
        await page.locator('[name=username]').fill(username);
        await page.locator('[name=password]').fill('DemoLocal123!');
        await Promise.all([page.waitForURL('**/dashboard/'), page.locator('button[type=submit]').click()]);
        for (const skill of ['listening', 'speaking', 'vocabulary']) {
            for (const width of [1920,1440,1024,991,768,390]) {
                await page.setViewportSize({width,height:1000});
                await page.goto(base+'/quan-ly/bai-tap/skill/'+skill+'/');
                await page.evaluate(() => document.fonts.ready);
                for (const open of [false,true]) {
                    await sidebar(open);
                    const layout = await page.evaluate(() => {
                        const table = document.querySelector('.lesson-bank-table');
                        const heading = document.querySelector('.lesson-bank-heading');
                        const title = heading.querySelector('h2').getBoundingClientRect();
                        const create = heading.querySelector('button').getBoundingClientRect();
                        const headers = [...table.tHead.rows[0].cells];
                        const rows = [...table.tBodies[0].rows].map(row => ({
                            cells:[...row.cells].map(cell => cell.textContent.trim()),
                            aligned:row.cells.length === headers.length && [...row.cells].every((cell,i) => {
                                const th=headers[i].getBoundingClientRect(), td=cell.getBoundingClientRect();
                                return Math.abs(th.left-td.left)<1 && Math.abs(th.right-td.right)<1;
                            })
                        }));
                        const header=table.tHead.getBoundingClientRect(), last=headers.at(-1).getBoundingClientRect();
                        return {
                            pageWidth:document.documentElement.scrollWidth, viewport:innerWidth,
                            headers:headers.map(cell => cell.textContent.trim()), rows,
                            headerGap:header.right-last.right,
                            uniformHeader:headers.every(cell => getComputedStyle(cell).backgroundColor === getComputedStyle(headers[0]).backgroundColor),
                            headingOverlap:title.left<create.right && title.right>create.left && title.top<create.bottom && title.bottom>create.top,
                            headingRight:Math.max(title.right, create.right)
                        };
                    });
                    const label = `${username} ${skill} ${width}px sidebar=${open}`;
                    assert.deepEqual(layout.headers, ['Buổi','Tên buổi','Chương trình','Số nội dung','Trạng thái','Thao tác'], label);
                    assert(layout.rows.length >= 2, label+' missing fixture rows');
                    for (const row of layout.rows) {
                        assert(row.aligned, label+' header and row cells do not align');
                        assert.match(row.cells[0], /^Buổi \d+$/, label);
                        assert(row.cells[1].length > 0, label+' missing title');
                        assert(['Dùng chung','TOEIC','B1','B2','VSTEP'].includes(row.cells[2]), label+' program column mismatch');
                        assert(/\d/.test(row.cells[3]), label+' content count column mismatch');
                        assert.match(row.cells[4], /Mở|Ẩn/, label);
                        assert.match(row.cells[5], /Quản lý bài tập/, label);
                    }
                    assert(Math.abs(layout.headerGap)<1, label+' blank header column');
                    assert(layout.uniformHeader, label+' inconsistent header background');
                    assert(layout.pageWidth<=layout.viewport+1, label+' page overflows horizontally');
                    assert(layout.headingRight<=layout.viewport+1, label+' heading exceeds viewport');
                    assert(!layout.headingOverlap, label+' heading overlaps create button');
                    results.push({username,skill,width,sidebar:open?'open':'closed',rows:layout.rows.length});
                    if (username==='demo_admin' && [1920,1024,390].includes(width))
                        await page.screenshot({path:path.join(output,`${skill}-${width}-${open?'open':'closed'}.png`),fullPage:true});
                }
            }
        }
        await context.close();
    }
    assert.deepEqual(errors, [], 'Browser console or HTTP errors');
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({cases:results.length,results,errors},null,2));
    console.log(`PASS: ${results.length} lesson-bank layouts, three skills, two roles, sidebar open/closed.`);
    await browser.close();
    server.kill();
})().catch(async error => {
    console.error(error.stack);
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({results,errors,error:error.message},null,2));
    if (page && !page.isClosed()) {
        fs.writeFileSync(path.join(output, 'failure.html'), await page.content());
        await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
    }
    await browser?.close();
    server?.kill();
    process.exitCode=1;
});
