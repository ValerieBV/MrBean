'use strict';
(()=>{
 const form=document.getElementById('listeningExerciseForm');if(!form)return;
 const kind=form.querySelector('[name=kind]'),count=form.querySelector('[name=question_count]'),pdf=form.querySelector('[name=document_file]'),key=form.querySelector('[name=answer_key]'),summary=document.getElementById('keySummary');
 const specs={part1:{count:6,letters:'ABCD'},part2:{count:25,letters:'ABC'},part3:{count:39,letters:'ABCD'},part4:{count:30,letters:'ABCD'},legacy:{count:null,letters:'ABCD'}};
 function update(){
  const spec=specs[kind.value];if(!spec)return;
  count.readOnly=spec.count!==null;if(spec.count!==null)count.value=spec.count;
  pdf.required=kind.value==='part1'&&form.dataset.hasDocument!=='true';
  document.getElementById('kindHelp').textContent=(spec.count?spec.count+' câu · ': 'Nhập số câu · ')+spec.letters.split('').join(' / ')+(kind.value==='part1'?' · cần PDF đề bài':'');
  const entries=(key.value.toUpperCase().match(/[A-D](?=$|[\s,;|])/g)||[]).length;
  summary.textContent=key.value.trim()?'Đang có khoảng '+entries+' đáp án. Hệ thống sẽ kiểm tra đủ số câu và đáp án trước khi lưu.':'Dán bảng đáp án hoặc tải CSV/TXT để tạo toàn bộ câu hỏi cùng lúc.';
 }
 kind.addEventListener('change',update);key.addEventListener('input',update);update();
 document.getElementById('downloadKeyTemplate').onclick=()=>{
  const spec=specs[kind.value],n=Number(count.value);if(!spec||!Number.isInteger(n)||n<1||n>200){summary.textContent='Chọn dạng bài và số câu trước khi tải mẫu.';return;}
  const csv=['number,answer,question_text,'+spec.letters.split('').join(','),...Array.from({length:n},(_,i)=>[i+1,'','',...spec.letters.split('').map(()=> '')].join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='dap-an-'+kind.value+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
})();
