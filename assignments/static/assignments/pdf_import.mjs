const form = document.getElementById('listeningExerciseForm');
if (form) {
    const assets = new URL('../core/vendor/pdfjs/', import.meta.url);
    const kind = form.elements.kind, field = form.elements.question_data, fileInput = form.elements.document_file;
    const wordInput = document.getElementById('docxQuestions'), wordButton = document.getElementById('readDOCX');
    const nav = document.getElementById('questionReviewNav'), editor = document.getElementById('questionEditor');
    const dialog = document.getElementById('questionReview'), reviewButton = document.getElementById('openQuestionReview');
    const status = document.getElementById('pdfImportStatus'), textButton = document.getElementById('readPDFText'), scanButton = document.getElementById('readPDFScan');
    const specs = {part1:{count:6,start:1,letters:'ABCD'},part2:{count:25,start:7,letters:'ABC'},part3:{count:39,start:32,letters:'ABCD'},part4:{count:30,start:71,letters:'ABCD'}};
    const states = new Map();
    let active = 0, busy = false, currentKind = kind.value, importedCount = null, importedSource = 'PDF';
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
        status.textContent='Đã đọc '+importedCount+'/'+spec().count+' câu từ '+importedSource+'. '+(issues?'Có '+issues+' câu cần kiểm tra. Chọn “Kiểm tra nội dung câu hỏi” để sửa.':'Dán đáp án đúng để lưu bài nghe.');
    }
    function openReview() {
        if(busy)return;
        if(form.elements.solution_data?.value && document.getElementById('solutionsReview')?.hidden === false){
            document.getElementById('solutionsReview').scrollIntoView({block:'start'});
            document.querySelector('#solutionsEditor textarea')?.focus({preventScroll:true});return;
        }
        if(!dialog.open)dialog.showModal();draw();
    }
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
        makeInput('Số câu trên đề','number');makeInput('Nội dung câu hỏi','question_text','textarea');
        [...spec().letters].forEach(letter=>makeInput('Lựa chọn '+letter,'option_'+letter.toLowerCase()));
        if(rows[active].uncertain){const note=document.createElement('p');note.className='listening-note';note.textContent='Câu này có phần nhận dạng chưa rõ. Kiểm tra lại với PDF.';editor.append(note);
            const confirm=document.createElement('button');confirm.type='button';confirm.className='listening-button secondary';confirm.textContent='Đã kiểm tra câu này';confirm.onclick=()=>{rows[active].uncertain=false;draw();};editor.append(confirm);}
        const controls=document.createElement('div');controls.className='listening-actions';
        for(const [label,change] of [['← Câu trước',-1],['Câu tiếp →',1]]){const b=document.createElement('button');b.type='button';b.className='listening-button secondary';b.textContent=label;b.disabled=active+change<0||active+change>=rows.length;b.onclick=()=>{active+=change;draw();};controls.append(b);}editor.append(controls);
    }
    function applyImport(imported, source='PDF') {
        const config=spec();
        if(!Array.isArray(imported))throw Error('Máy chủ trả về danh sách câu hỏi không hợp lệ. Thử đọc lại tài liệu.');
        if(!imported.length){status.textContent=kind.value==='part1'?'PDF tranh đã được chọn; các lựa chọn được nghe trong audio.':'Chưa tách được câu hỏi từ PDF. Dùng file Word .docx hoặc chọn “Đọc bản scan bằng AI”.';return;}
        if(imported.length>config.count)throw Error('Tài liệu có nhiều câu hơn dạng đã chọn. Tách riêng phần cần dùng.');
        const start=kind.value==='part4'?71:imported[0].number,next=Array.from({length:config.count},(_,i)=>blank(start+i));
        for(const row of imported){const index=row.number-start;if(index<0||index>=config.count)throw Error('Số câu trong tài liệu không đúng phần đã chọn. Kiểm tra lại phần đề đã chọn.');next[index]={...blank(row.number),...row};}
        rows=next;active=0;importedCount=imported.length;importedSource=source;draw();
    }
    async function request(body,isJSON=false) {
        const headers={'X-CSRFToken':form.elements.csrfmiddlewaretoken.value};if(isJSON)headers['Content-Type']='application/json';
        const response=await fetch(form.dataset.extractUrl,{method:'POST',headers,body:isJSON?JSON.stringify(body):body});
        if(response.status===401||response.redirected)throw Error('Phiên đăng nhập đã hết. Tải lại trang và đăng nhập để tiếp tục.');
        const data=await response.json().catch(()=>null);if(!data)throw Error('Máy chủ chưa đọc được tài liệu (HTTP '+response.status+'). Thử lại hoặc dùng Word .docx.');if(!response.ok)throw Error(data.message||'Không đọc được PDF. Kiểm tra lại tài liệu.');return data;
    }
    function setBusy(value) { busy=value;form.dataset.pdfBusy=String(value);textButton.disabled=scanButton.disabled=reviewButton.disabled=wordButton.disabled=kind.disabled=fileInput.disabled=wordInput.disabled=value;form.querySelector('[type=submit]').disabled=value;form.dispatchEvent(new Event('listening-questions-changed')); }
    async function readText() {
        if(busy || form.dataset.solutionsBusy==='true')return;
        if(form.elements.solution_data?.value && document.getElementById('solutionsReview')?.hidden === false){status.textContent='Đã chọn PDF đề bài.';return;}
        setBusy(true);status.textContent='Đang đọc PDF…';let loadingTask;
        try {
            const file=fileInput.files[0];
            if(!file&&!form.dataset.documentUrl)throw Error('Chọn file PDF hoặc dùng mục Word .docx bên dưới.');
            wordInput.value='';
            if(file)resetQuestions();
            if(file && file.size>25*1024*1024)throw Error('PDF tối đa 25 MiB.');
            const bytes=file?await file.arrayBuffer():form.dataset.documentUrl?await (await fetch(form.dataset.documentUrl)).arrayBuffer():null;
            if(!bytes)throw Error('Chọn file PDF trước khi đọc câu hỏi.');
            let pdfjs;
            try{pdfjs=await import('../core/vendor/pdfjs/pdf.min.mjs');}catch{throw Error('Chưa tải được bộ đọc PDF. Nhấn Ctrl + F5 hoặc dùng Word .docx.');}
            pdfjs.GlobalWorkerOptions.workerSrc=new URL('pdf.worker.min.mjs',assets).href;
            loadingTask=pdfjs.getDocument({data:new Uint8Array(bytes),isEvalSupported:false,enableXfa:false,standardFontDataUrl:new URL('standard_fonts/',assets).href,wasmUrl:new URL('wasm/',assets).href});
            const pdf=await loadingTask.promise;
            if(pdf.numPages>40)throw Error('Tách PDF còn tối đa 40 trang cho một bài nghe.');
            const pages=[];
            for(let n=1;n<=pdf.numPages;n++){const page=await pdf.getPage(n),text=await page.getTextContent();pages.push({width:page.getViewport({scale:1}).width,items:text.items.filter(item=>item.str!==undefined).map(item=>({text:item.str,x:item.transform[4],y:item.transform[5]}))});}
            if(!pages.some(page=>page.items.some(item=>item.text.trim()))){status.textContent=kind.value==='part1'?'PDF tranh đã được chọn; các lựa chọn được nghe trong audio.':'PDF không có chữ đọc được, có thể là bản scan. Chọn “Đọc bản scan bằng AI” hoặc tải Word .docx có văn bản.';return;}
            const data=await request({kind:kind.value,pages},true);applyImport(data.questions);
        }catch(error){status.textContent=error.name==='PasswordException'?'PDF có mật khẩu. Dùng bản PDF đã mở khóa.':error.name==='InvalidPDFException'?'PDF không hợp lệ hoặc bị hỏng. Xuất lại PDF hoặc dùng Word .docx.':error.message;}
        finally{try{await loadingTask?.destroy();}finally{setBusy(false);}}
    }
    async function readScan() {
        if(busy || form.dataset.solutionsBusy==='true')return;setBusy(true);status.textContent='Đang nhận dạng PDF bằng AI…';
        try{wordInput.value='';if(fileInput.files[0])resetQuestions();const body=new FormData();body.set('kind',kind.value);if(fileInput.files[0])body.set('document_file',fileInput.files[0]);else if(form.dataset.exerciseId)body.set('exercise_id',form.dataset.exerciseId);else throw Error('Chọn file PDF trước khi nhận dạng.');
            const data=await request(body);applyImport(data.questions);
        }catch(error){status.textContent=error.message;}finally{setBusy(false);}
    }
    function resetQuestions() {rows=[];active=0;importedCount=null;draw();}
    async function readWord() {
        if(busy || form.dataset.solutionsBusy==='true')return;
        const file=wordInput.files[0];if(!file){status.textContent='Chọn file Word .docx trước khi đọc câu hỏi.';return;}
        setBusy(true);resetQuestions();status.textContent='Đang đọc câu hỏi từ Word…';
        try{
            if(!file.name.toLowerCase().endsWith('.docx'))throw Error('Chọn file .docx. Với .doc cũ, mở Word và lưu lại thành .docx.');
            if(file.size>10*1024*1024)throw Error('Word tối đa 10 MiB.');
            const body=new FormData();body.set('kind',kind.value);body.set('docx_file',file);
            const data=await request(body);applyImport(data.questions,'Word');
        }catch(error){status.textContent=error.message;}finally{setBusy(false);}
    }
    kind.addEventListener('change',()=>{dialog.close();states.set(currentKind,rows);currentKind=kind.value;rows=states.get(currentKind)||[];active=0;importedCount=null;status.textContent='';draw();if(!['part3','part4'].includes(kind.value))wordInput.value='';else if(wordInput.files[0])readWord();});
    textButton.onclick=readText;scanButton.onclick=readScan;fileInput.addEventListener('change',()=>{if(wordInput.files[0]&&['part3','part4'].includes(kind.value))return;readText();});
    wordInput.addEventListener('change',readWord);wordButton.onclick=readWord;
    reviewButton.onclick=openReview;
    dialog.querySelectorAll('[data-review-close]').forEach(button=>button.onclick=()=>dialog.close());
    dialog.addEventListener('close',()=>{editor.querySelectorAll('input,textarea').forEach(input=>input.disabled=true);sync();importStatus();});
    form.addEventListener('submit',event=>{sync();if(dialog.open){event.preventDefault();dialog.close();}});
    form.addEventListener('listening-solutions-imported',event=>{if(['part3','part4'].includes(kind.value))applyImport(event.detail,'Word');});
    draw();
    if(wordInput.files[0])readWord();else if(fileInput.files[0])readText();
}
