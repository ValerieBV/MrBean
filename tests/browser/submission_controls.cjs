'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const script = fs.readFileSync(path.resolve(__dirname, '../../submissions/static/submissions/submit.js'), 'utf8');
const listeningScript = fs.readFileSync(path.resolve(__dirname, '../../submissions/static/submissions/listening.js'), 'utf8');
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const controls = '<p id="submissionStatus"></p><button type="submit" id="submitButton" disabled>Nộp bài</button>';

function page(body) {
    const dom = new JSDOM(body, {url:'https://mrbean.test/task/', runScripts:'outside-only'});
    const w = dom.window;
    w.HTMLMediaElement.prototype.pause = () => {};
    w.URL.createObjectURL = () => 'blob:preview';
    w.URL.revokeObjectURL = () => {};
    return {dom, w, document:w.document};
}

async function listening() {
    const question = id => `<fieldset data-question data-number="${id}" data-requires-short-answer="true"><input type="radio" name="q_${id}" value="B" checked><textarea name="s_${id}" class="listening-answer">response ${id}</textarea></fieldset>`;
    const panel = (order, id) => `<section data-listening-exercise="${order}"><div class="listening-question-nav"></div>${question(id)}<button type="button" data-question-prev></button><span class="question-counter"></span><button type="button" data-question-next></button><button type="submit" data-submit-exercise="${id}">Nộp bài ${order}</button></section>`;
    const {dom, w, document} = page(`<button data-listening-tab="1"></button><button data-listening-tab="2"></button><form id="submissionForm" data-kind="listening" data-submit-url="/submit" data-draft-url="/draft"><input name="csrfmiddlewaretoken" value="token"><input name="reference_version" value="v1"><p id="listeningProgress"></p><p id="draftStatus"></p><p id="submissionStatus"></p>${panel(1,11)}${panel(2,22)}</form>`);
    const calls = [];
    let rejectSubmission = true;
    w.fetch = async (url, request) => {
        calls.push({url, request});
        if(url === '/draft') return {ok:true, json:async () => ({saved_at:'2026-11-23T10:00:00Z'})};
        return rejectSubmission ? {ok:false, json:async () => ({message:'Try again'})} : {ok:true, json:async () => ({detail_url:'#done'})};
    };
    w.eval(script);
    w.eval(listeningScript);
    document.querySelector('[data-listening-tab="2"]').click();
    assert.equal(document.querySelector('[data-listening-exercise="1"]').hidden, true);
    document.querySelector('[name=s_11]').dispatchEvent(new w.Event('input', {bubbles:true}));
    const form = document.getElementById('submissionForm');
    const submitter = document.querySelector('[data-submit-exercise="22"]');
    await form.onsubmit(new w.SubmitEvent('submit', {submitter, cancelable:true}));
    const draft = JSON.parse(calls.find(call => call.url === '/draft').request.body);
    assert.deepEqual(Object.keys(draft.answers).sort(), ['11','22']);
    const submitted = calls.find(call => call.url === '/submit').request.body;
    assert.equal(submitted.get('exercise_id'), '22');
    assert.deepEqual(JSON.parse(submitted.get('answers')), {'22':{chosen:'B',short_answer:'response 22'}});
    assert.equal(document.getElementById('submissionStatus').textContent, 'Try again');
    assert([...document.querySelectorAll('[data-submit-exercise]')].every(button => !button.disabled));
    assert.equal(document.querySelector('[name=s_11]').value, 'response 11');
    rejectSubmission = false;
    const hiddenSubmitter = document.querySelector('[data-submit-exercise="11"]');
    await form.onsubmit(new w.SubmitEvent('submit', {submitter:hiddenSubmitter, cancelable:true}));
    assert.equal(w.location.hash, '#done');
    assert.equal(calls.filter(call => call.url === '/submit').length, 2);
    assert.equal(calls.filter(call => call.url === '/submit')[1].request.body.get('exercise_id'), '22');
    dom.window.close();
}

async function recording({stopPaused=false, denied=false}={}) {
    const {dom, w, document} = page(`<form id="submissionForm" data-kind="speaking" data-submit-url="/submit"><input name="csrfmiddlewaretoken" value="token"><button type="button" id="recordStart">Ghi âm</button><button type="button" id="recordPause" disabled>Tạm dừng</button><button type="button" id="recordStop" disabled>Dừng ghi âm</button><p id="recordStatus"></p><audio id="recordPreview" hidden></audio>${controls}</form>`);
    let recorder, released=0, posted;
    w.navigator.mediaDevices = {getUserMedia:async () => {
        if(denied){const error=new Error('Permission denied');error.name='NotAllowedError';throw error;}
        return {getTracks:() => [{stop:() => {released++;}}]};
    }};
    w.MediaRecorder = class {
        static isTypeSupported() {return true;}
        constructor() {this.state='inactive';recorder=this;}
        start() {this.state='recording';}
        pause() {this.state='paused';this.onpause();}
        resume() {this.state='recording';this.onresume();}
        stop() {this.state='inactive';this.onstop();}
        chunk(text) {assert.equal(this.state,'recording');this.ondataavailable({data:new w.Blob([text])});}
    };
    w.fetch = async (url, request) => {posted=request.body;return {ok:true,json:async () => ({detail_url:'#done'})};};
    w.eval(script);
    await document.getElementById('recordStart').onclick();
    if(denied){
        assert.match(document.getElementById('recordStatus').textContent, /chưa cho phép/);
        assert.equal(document.getElementById('recordStart').disabled,false);
        assert.equal(document.getElementById('submitButton').disabled,true);
        dom.window.close();return;
    }
    recorder.chunk('BEFORE');
    document.getElementById('recordPause').click();
    assert.equal(recorder.state,'paused');
    assert.equal(document.getElementById('recordPause').textContent,'Tiếp tục ghi âm');
    assert.equal(document.getElementById('recordStop').disabled,false);
    assert.equal(document.getElementById('submitButton').disabled,true);
    const unload = new w.Event('beforeunload',{cancelable:true});
    w.dispatchEvent(unload);
    assert.equal(unload.defaultPrevented,true);
    await document.getElementById('submissionForm').onsubmit(new w.Event('submit',{cancelable:true}));
    assert.equal(posted,undefined);
    if(!stopPaused){
        document.getElementById('recordPause').click();
        assert.equal(recorder.state,'recording');
        recorder.chunk('AFTER');
    }
    document.getElementById('recordStop').click();
    assert.equal(released,1);
    assert.equal(document.getElementById('recordPreview').hidden,false);
    assert.equal(document.getElementById('submitButton').disabled,false);
    await document.getElementById('submissionForm').onsubmit(new w.Event('submit',{cancelable:true}));
    assert.equal(posted.get('audio').size,stopPaused?6:11);
    assert.equal(posted.get('audio').name,'recording.webm');
    assert.equal(w.location.hash,'#done');
    dom.window.close();
}

(async () => {
    await listening();
    await recording();
    await recording({stopPaused:true});
    await recording({denied:true});
    await tick();
    process.stdout.write('PASS: scoped listening payloads, draft preservation, retry, recorder pause/resume, stop while paused, microphone denial.\n');
})().catch(error => {process.stderr.write(error.stack+'\n');process.exitCode=1;});
