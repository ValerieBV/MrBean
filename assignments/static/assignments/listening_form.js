'use strict';
(()=>{
 const form=document.getElementById('listeningExerciseForm');if(!form)return;
 const kind=form.querySelector('[name=kind]'),count=form.querySelector('[name=question_count]'),pdf=form.querySelector('[name=document_file]'),key=form.querySelector('[name=answer_key]'),summary=document.getElementById('keySummary');
 function questionNumbers(total){let rows=[];try{rows=JSON.parse(form.elements.question_data.value||'[]');}catch{}return rows.length===total?rows.map(row=>row.number):Array.from({length:total},(_,i)=>( {part1:1,part2:7,part3:32,part4:71}[kind.value]||1)+i);}
 const specs={part1:{count:6,letters:'ABCD'},part2:{count:25,letters:'ABC'},part3:{count:39,letters:'ABCD'},part4:{count:30,letters:'ABCD'},legacy:{count:null,letters:'ABCD'}};
 function update(){
  const spec=specs[kind.value];if(!spec)return;
  const audioOnly=kind.value==='part2',pdfField=form.querySelector('[data-pdf-field]');
  const hasSolutions=form.dataset.hasSolutions==='true';
  pdfField.hidden=audioOnly;pdfField.querySelectorAll('input,button').forEach(control=>control.disabled=audioOnly||form.dataset.pdfBusy==='true'||hasSolutions&&control.tagName==='BUTTON');
  const wordField=form.querySelector('[data-docx-field]');wordField.hidden=hasSolutions||!['part3','part4'].includes(kind.value);
  wordField.querySelectorAll('input,button').forEach(control=>control.disabled=wordField.hidden||form.dataset.pdfBusy==='true');
  document.getElementById('openQuestionReview').hidden=hasSolutions||['part1','part2'].includes(kind.value);
  if(['part1','part2'].includes(kind.value)&&document.getElementById('questionReview').open)document.getElementById('questionReview').close();
  count.readOnly=spec.count!==null;if(spec.count!==null)count.value=spec.count;
  pdf.required=kind.value==='part1'&&form.dataset.hasDocument!=='true';
  document.getElementById('selectedKindTitle').textContent=kind.options[kind.selectedIndex].textContent;
  document.getElementById('selectedKindMeta').textContent=(count.value?count.value+' câu · ':'')+spec.letters.length+' đáp án mỗi câu'+(kind.value==='part1'?' · cần file nghe và PDF':' · cần file nghe');
  const total=Number(count.value)||6,numbers=questionNumbers(total);
  if(kind.value==='part2'||kind.value==='part4')document.getElementById('selectedKindMeta').textContent='Câu '+numbers[0]+'–'+numbers[total-1]+' · '+total+' câu · '+(audioOnly?'chỉ file nghe, chọn A/B/C':'4 lựa chọn mỗi câu');
  const entries=(key.value.toUpperCase().match(/[A-D](?=$|[\s,;|])/g)||[]).length;
  summary.textContent=key.value.trim()?entries+'/'+total+' đáp án':'';
 }
 kind.addEventListener('change',update);key.addEventListener('input',update);form.addEventListener('listening-questions-changed',update);update();
 document.getElementById('downloadKeyTemplate').onclick=()=>{
  const spec=specs[kind.value],n=Number(count.value);if(!spec||!Number.isInteger(n)||n<1||n>200){summary.textContent='Chọn dạng bài và số câu trước khi tải mẫu.';return;}
  const csv=['number,answer,question_text,'+spec.letters.split('').join(','),...Array.from({length:n},(_,i)=>[questionNumbers(n)[i],'','',...spec.letters.split('').map(()=> '')].join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='dap-an-'+kind.value+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
})();
