import {getDocument, GlobalWorkerOptions} from '../core/vendor/pdfjs/pdf.min.mjs';

const form = document.getElementById('listeningExerciseForm');
if (form) {
    const assets = new URL('../core/vendor/pdfjs/', import.meta.url);
    GlobalWorkerOptions.workerSrc = new URL('pdf.worker.min.mjs', assets).href;
    const kind = form.elements.kind, field = form.elements.question_data, fileInput = form.elements.document_file;
    const nav = document.getElementById('questionReviewNav'), editor = document.getElementById('questionEditor');
    const dialog = document.getElementById('questionReview'), reviewButton = document.getElementById('openQuestionReview');
    const status = document.getElementById('pdfImportStatus'), textButton = document.getElementById('readPDFText'), scanButton = document.getElementById('readPDFScan');
    const specs = {part1:{count:6,start:1,letters:'ABCD'},part2:{count:25,start:7,letters:'ABC'},part3:{count:39,start:32,letters:'ABCD'},part4:{count:30,start:71,letters:'ABCD'}};
    const states = new Map();
    let active = 0, busy = false, currentKind = kind.value, importedCount = null;
    let rows;
    try { rows = JSON.parse(field.value || '[]'); } catch { rows = []; }
    function spec() { return specs[kind.value] || {count:Number(form.elements.question_count.value)||1,start:1,letters:'ABCD'}; }
    function blank(number) { return {number,question_text:'',option_a:'',option_b:'',option_c:'',option_d:'',uncertain:false}; }
    function ensureRows() {
        const config = spec();
        if (!Array.isArray(rows) || rows.length !== config.count) rows = Array.from({length:config.count}, (_,i)=>blank(config.start+i));
        rows = rows.map(row=>({...blank(row.number),...row}));
    }
    function complete(row) {
        return !row.uncertain && row.question_text.trim() && [...spec().letters].every(c=>row['option_'+c.toLowerCase()].trim() && row['option_'+c.toLowerCase()].trim()!==c);
    }
    function sync() { field.value = JSON.stringify(rows);form.dispatchEvent(new Event('listening-questions-changed')); }
    function importStatus() {
        if(importedCount===null)return;
        const issues=['part3','part4'].includes(kind.value)?rows.filter(row=>!complete(row)).length:0;
        status.textContent='Đã đọc '+importedCount+'/'+spec().count+' câu. '+(issues?'Có '+issues+' câu cần kiểm tra. Chọn “Kiểm tra nội dung PDF” để sửa.':'Dán đáp án đúng để lưu bài nghe.');
    }
    function openReview() {if(busy)return;if(!dialog.open)dialog.showModal();draw();}
    function drawNav() {
        nav.replaceChildren();
        rows.forEach((row,index)=>{
            const button = document.createElement('button');button.type='button';button.textContent=row.number;
            button.className='question-number'+(complete(row)?' answered':'')+(index===active?' current':'');
            button.setAttribute('aria-label','Kiểm tra câu '+row.number);button.setAttribute('aria-pressed',String(index===active));
            button.onclick=()=>{active=index;draw();};nav.append(button);
        });
        document.getElementById('questionReviewCount').textContent=rows.filter(complete).length+'/'+rows.length+' câu có nội dung';
        sync();importStatus();
    }
    function makeInput(label,key,tag='input') {
        const wrapper=document.createElement('div');wrapper.className='listening-field';
        const title=document.createElement('label'),input=document.createElement(tag);input.id='review_'+key;input.name='review_'+key;
        title.htmlFor=input.id;title.textContent=label;input.value=rows[active][key] ?? '';input.disabled=!dialog.open;
        if(key==='number'){input.type='number';input.min='1';input.max='9999';}
        else {input.maxLength=tag==='textarea'?10000:255;if(tag==='textarea')input.rows=3;}
        input.addEventListener('input',()=>{rows[active][key]=key==='number'?Number(input.value):input.value;drawNav();});
        wrapper.append(title,input);editor.append(wrapper);
    }
    function draw() {
        ensureRows();active=Math.min(active,rows.length-1);editor.replaceChildren();drawNav();
        const heading=document.createElement('h3');heading.textContent='Câu '+rows[active].number;editor.append(heading);
        makeInput('Số câu trên PDF','number');makeInput('Nội dung câu hỏi','question_text','textarea');
        [...spec().letters].forEach(letter=>makeInput('Lựa chọn '+letter,'option_'+letter.toLowerCase()));
        if(rows[active].uncertain){const note=document.createElement('p');note.className='listening-note';note.textContent='Câu này có phần nhận dạng chưa rõ. Kiểm tra lại với PDF.';editor.append(note);
            const confirm=document.createElement('button');confirm.type='button';confirm.className='listening-button secondary';confirm.textContent='Đã kiểm tra câu này';confirm.onclick=()=>{rows[active].uncertain=false;draw();};editor.append(confirm);}
        const controls=document.createElement('div');controls.className='listening-actions';
        for(const [label,change] of [['← Câu trước',-1],['Câu tiếp →',1]]){const b=document.createElement('button');b.type='button';b.className='listening-button secondary';b.textContent=label;b.disabled=active+change<0||active+change>=rows.length;b.onclick=()=>{active+=change;draw();};controls.append(b);}editor.append(controls);
    }
    function applyImport(imported) {
        const config=spec();
        if(!imported.length){status.textContent=['part1','part2'].includes(kind.value)?'PDF không có câu hỏi in sẵn. Với dạng này, học viên có thể nghe các lựa chọn trong audio; không cần tạo thêm lời đọc.':'PDF chưa có câu hỏi đọc được. Với PDF scan, chọn “Đọc bản scan bằng AI”.';return;}
        if(imported.length>config.count)throw Error('PDF có nhiều câu hơn dạng đã chọn. Tách riêng phần cần dùng.');
        const start=kind.value==='part4'?71:imported[0].number,next=Array.from({length:config.count},(_,i)=>blank(start+i));
        for(const row of imported){const index=row.number-start;if(index<0||index>=config.count)throw Error('Số câu trong PDF không liên tục. Kiểm tra lại phần đề đã chọn.');next[index]={...blank(row.number),...row};}
        rows=next;active=0;importedCount=imported.length;draw();
    }
    async function request(body,isJSON=false) {
        const headers={'X-CSRFToken':form.elements.csrfmiddlewaretoken.value};if(isJSON)headers['Content-Type']='application/json';
        const response=await fetch(form.dataset.extractUrl,{method:'POST',headers,body:isJSON?JSON.stringify(body):body});
        if(response.status===401||response.redirected)throw Error('Phiên đăng nhập đã hết. Tải lại trang và đăng nhập để tiếp tục.');
        const data=await response.json();if(!response.ok)throw Error(data.message||'Không đọc được PDF. Kiểm tra lại tài liệu.');return data;
    }
    function setBusy(value) { busy=value;form.dataset.pdfBusy=String(value);textButton.disabled=scanButton.disabled=reviewButton.disabled=kind.disabled=fileInput.disabled=value;form.querySelector('[type=submit]').disabled=value; }
    async function readText() {
        if(busy)return;setBusy(true);status.textContent='Đang đọc PDF…';let loadingTask;
        try {
            const file=fileInput.files[0];
            if(file && file.size>25*1024*1024)throw Error('PDF tối đa 25 MiB.');
            const bytes=file?await file.arrayBuffer():form.dataset.documentUrl?await (await fetch(form.dataset.documentUrl)).arrayBuffer():null;
            if(!bytes)throw Error('Chọn file PDF trước khi đọc câu hỏi.');
            loadingTask=getDocument({data:new Uint8Array(bytes),isEvalSupported:false,enableXfa:false,standardFontDataUrl:new URL('standard_fonts/',assets).href,wasmUrl:new URL('wasm/',assets).href});
            const pdf=await loadingTask.promise;
            if(pdf.numPages>40)throw Error('Tách PDF còn tối đa 40 trang cho một bài nghe.');
            const pages=[];
            for(let n=1;n<=pdf.numPages;n++){const page=await pdf.getPage(n),text=await page.getTextContent();pages.push({width:page.getViewport({scale:1}).width,items:text.items.filter(item=>item.str!==undefined).map(item=>({text:item.str,x:item.transform[4],y:item.transform[5]}))});}
            const data=await request({kind:kind.value,pages},true);applyImport(data.questions);
        }catch(error){status.textContent=error.name==='PasswordException'?'PDF có mật khẩu. Dùng bản PDF đã mở khóa.':error.message;}
        finally{try{await loadingTask?.destroy();}finally{setBusy(false);}}
    }
    async function readScan() {
        if(busy)return;setBusy(true);status.textContent='Đang nhận dạng PDF bằng AI…';
        try{const body=new FormData();body.set('kind',kind.value);if(fileInput.files[0])body.set('document_file',fileInput.files[0]);else if(form.dataset.exerciseId)body.set('exercise_id',form.dataset.exerciseId);else throw Error('Chọn file PDF trước khi nhận dạng.');
            const data=await request(body);applyImport(data.questions);
        }catch(error){status.textContent=error.message;}finally{setBusy(false);}
    }
    kind.addEventListener('change',()=>{dialog.close();states.set(currentKind,rows);currentKind=kind.value;rows=states.get(currentKind)||[];active=0;importedCount=null;status.textContent='';draw();});
    textButton.onclick=readText;scanButton.onclick=readScan;fileInput.addEventListener('change',readText);
    reviewButton.onclick=openReview;
    dialog.querySelectorAll('[data-review-close]').forEach(button=>button.onclick=()=>dialog.close());
    dialog.addEventListener('close',()=>{editor.querySelectorAll('input,textarea').forEach(input=>input.disabled=true);sync();importStatus();});
    form.addEventListener('submit',event=>{sync();if(dialog.open){event.preventDefault();dialog.close();}});
    draw();
}
