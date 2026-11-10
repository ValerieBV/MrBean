'use strict';
(() => {
    const form = document.getElementById('listeningExerciseForm') || document.getElementById('listeningSolutionsForm');
    if (!form) return;
    const kind = form.elements.kind, hidden = form.elements.solution_data, upload = form.elements.solutions_file;
    const read = document.getElementById('readSolutionsWord'), status = document.getElementById('solutionsStatus');
    const review = document.getElementById('solutionsReview'), nav = document.getElementById('solutionsNav'), editor = document.getElementById('solutionsEditor');
    const template = document.getElementById('downloadSolutionsTemplate');
    let bundle = {}, active = 0, busy = false;
    try { bundle = JSON.parse(hidden.value || '{}'); } catch {}
    function sync(questionsChanged = true) {
        hidden.value = bundle.questions?.length ? JSON.stringify(bundle) : '';
        if (!bundle.questions?.length) return;
        if (form.elements.answer_key) {
            const key = bundle.questions.map(row => row.number + '.' + row.answer).join('\n');
            if (form.elements.answer_key.value !== key) {
                form.elements.answer_key.value = key;
                form.elements.answer_key.dispatchEvent(new Event('input'));
            }
        }
        if (questionsChanged && form.elements.question_data && ['part3','part4'].includes(kind.value)) {
            const questions = bundle.questions.map(row => Object.fromEntries(['number','question_text','option_a','option_b','option_c','option_d'].map(key=>[key,row[key] || ''])));
            hidden.value = JSON.stringify(bundle);
            form.elements.question_data.value = JSON.stringify(questions);
            form.dispatchEvent(new CustomEvent('listening-solutions-imported', {detail: questions}));
        }
    }
    function input(parent, label, row, key, rows = 3) {
        const box = document.createElement('div'), title = document.createElement('label');
        const control = document.createElement(key === 'answer' ? 'select' : 'textarea');
        box.className = 'listening-field';
        control.id = 'solution_' + (row.number || row.start) + '_' + key;
        title.htmlFor = control.id; title.textContent = label;
        if (key === 'answer') {
            for (const letter of kind.value === 'part2' ? 'ABC' : 'ABCD') {
                const option = document.createElement('option'); option.value = option.textContent = letter; control.append(option);
            }
        } else {
            control.rows = rows; control.maxLength = key.startsWith('option_') ? 255 : key === 'text' || (!row.number && key === 'translation') ? 20000 : 10000;
        }
        control.value = row[key] || '';
        control.disabled = busy;
        control.addEventListener('input', () => { row[key] = control.value; sync(key === 'question_text' || key.startsWith('option_')); });
        box.append(title, control); parent.append(box);
    }
    function draw() {
        const hasSolutions = Boolean(bundle.questions?.length);
        form.dataset.hasSolutions = String(hasSolutions);
        form.dispatchEvent(new Event('listening-questions-changed'));
        if (form.elements.answer_key) form.elements.answer_key.readOnly = hasSolutions;
        if (form.elements.answer_key_file) form.elements.answer_key_file.disabled = hasSolutions;
        template.hidden = kind.value === 'legacy';
        template.href = template.dataset.templateUrl.replace('part1', kind.value);
        read.disabled = busy || kind.value === 'legacy'; upload.disabled = busy || kind.value === 'legacy';
        review.hidden = !bundle.questions?.length;
        nav.replaceChildren(); editor.replaceChildren();
        if (review.hidden) return;
        const size = ['part3','part4'].includes(kind.value) ? 3 : 1;
        const total = Math.ceil(bundle.questions.length / size);
        active = Math.min(active, total - 1);
        for (let index = 0; index < total; index++) {
            const first = bundle.questions[index*size], last = bundle.questions[Math.min((index+1)*size-1,bundle.questions.length-1)];
            const button = document.createElement('button'); button.type = 'button';
            button.className = 'question-number' + (active === index ? ' current' : '');
            button.textContent = size === 3 ? first.number + '–' + last.number : first.number;
            button.setAttribute('aria-label', 'Xem lời giải câu ' + button.textContent);
            button.setAttribute('aria-pressed', String(active === index));
            button.disabled = busy;
            button.onclick = () => { active = index; draw(); }; nav.append(button);
        }
        const questions = bundle.questions.slice(active*size, (active+1)*size);
        const passage = bundle.passages?.find(p => p.start === questions[0].number);
        const heading = document.createElement('h3'); heading.textContent = size === 3 ? 'Đoạn ' + questions[0].number + '–' + questions.at(-1).number : 'Câu ' + questions[0].number;
        editor.append(heading);
        if (passage) {
            const shared = document.createElement('section'); shared.className = 'solution-passage-editor';
            input(shared, kind.value === 'part3' ? 'Hội thoại dùng chung' : 'Đoạn nói dùng chung', passage, 'text', 8);
            input(shared, 'Bản dịch đoạn nghe', passage, 'translation', 5); editor.append(shared);
        }
        for (const question of questions) {
            const card = document.createElement('section'); card.className = 'solution-question-editor';
            const title = document.createElement('h4'); title.textContent = 'Câu ' + question.number; card.append(title);
            input(card, kind.value === 'part1' ? 'Nội dung nghe' : 'Câu hỏi', question, 'question_text');
            const options = document.createElement('div'); options.className = 'solution-option-editor';
            for (const letter of kind.value === 'part2' ? 'ABC' : 'ABCD') input(options, 'Lựa chọn ' + letter, question, 'option_'+letter.toLowerCase(), 2);
            card.append(options); input(card, 'Đáp án đúng', question, 'answer'); input(card, 'Giải thích đáp án', question, 'explanation', 5);
            const translation = document.createElement('details'), summary = document.createElement('summary');
            summary.textContent = 'Bản dịch câu hỏi và lựa chọn'; translation.append(summary);
            input(translation, 'Bản dịch', question, 'translation', 4); card.append(translation); editor.append(card);
        }
    }
    async function readWord() {
        if (busy || form.dataset.pdfBusy === 'true') return;
        const file = upload.files[0];
        if (!file) { status.textContent = 'Chọn file Word .docx.'; return; }
        if (!file.name.toLowerCase().endsWith('.docx') || file.size > 10*1024*1024) { status.textContent = 'Chỉ nhận file Word .docx tối đa 10 MiB.'; return; }
        form.elements.solutions_previewed.value = '';
        busy = true; form.dataset.solutionsBusy = 'true'; const selectedKind = kind.value;
        const submit = form.querySelector('[type=submit]'); submit.disabled = true;
        if (kind.tagName === 'SELECT') kind.disabled = true;
        draw(); status.textContent = 'Đang đọc đáp án và giải thích…';
        try {
            const body = new FormData(); body.set('kind', selectedKind); body.set('solutions_file', file);
            const response = await fetch(form.dataset.solutionsUrl, {method:'POST',headers:{'X-CSRFToken':form.elements.csrfmiddlewaretoken.value},body});
            if (response.redirected || response.status === 401) throw Error('Phiên đăng nhập đã hết. Đăng nhập lại để tiếp tục.');
            const data = await response.json().catch(()=>null);
            if (!response.ok || !data?.solutions) throw Error(data?.message || 'Không đọc được file Word.');
            bundle = data.solutions; active = 0; form.elements.solutions_previewed.value = 'True';
            if (form.elements.answer_key_file) form.elements.answer_key_file.value = '';
            sync(); status.textContent = 'Đã đọc ' + bundle.questions.length + ' lời giải' + (bundle.passages.length ? ' · ' + bundle.passages.length + ' đoạn nghe' : '') + '.';
        } catch (error) { status.textContent = error.message; }
        finally { busy = false; form.dataset.solutionsBusy = 'false'; submit.disabled = false; if (kind.tagName === 'SELECT') kind.disabled = false; draw(); }
    }
    kind.addEventListener('change', () => { bundle = {}; active = 0; hidden.value = ''; upload.value = ''; form.elements.solutions_previewed.value = '';  status.textContent = ''; draw(); });
    upload.addEventListener('change', () => { form.elements.solutions_previewed.value = ''; readWord(); }); read.onclick = readWord;
    form.addEventListener('submit', event => { if (busy) event.preventDefault(); else sync(); });
    draw(); if (bundle.questions?.length) sync();
})();
