'use strict';
(()=>{
const form=document.getElementById('submissionForm');
if(!form)return;
const statusBox=document.getElementById('submissionStatus'),submitButton=document.getElementById('submitButton');
const speaking=form.dataset.kind==='speaking';
let recording=null,stream=null,blob=null,previewURL=null,requesting=false,disposed=false,uploading=false;
const start=document.getElementById('recordStart'),stop=document.getElementById('recordStop'),preview=document.getElementById('recordPreview'),recordStatus=document.getElementById('recordStatus');
const maxBytes=20*1024*1024;
let draftTimer=null,draftRequest=Promise.resolve(),draftDirty=false;
function collectAnswers(data){const answers={};for(const[key,value]of data){if(key.startsWith('q_')||key.startsWith('s_')){const id=key.slice(2);answers[id]??={chosen:'',short_answer:''};answers[id][key.startsWith('q_')?'chosen':'short_answer']=value;}}return answers;}
function draftData(){const data=new FormData(form);return{text:data.get('text')||'',answers:collectAnswers(data),reference_version:data.get('reference_version')};}
function listeningProgress(){const box=document.getElementById('listeningProgress');if(!box)return;const questions=[...form.querySelectorAll('[data-question]')],done=questions.filter(q=>q.querySelector('input[type=radio]:checked')&&(q.dataset.requiresShortAnswer!=='true'||/[\p{L}\p{N}]/u.test(q.querySelector('.listening-answer')?.value||'')));box.textContent='Đã trả lời '+done.length+'/'+questions.length+' câu';}
function saveDraft(){
 if(speaking||uploading||!form.dataset.draftUrl||!draftDirty)return draftRequest;
 draftDirty=false;const data=draftData(),box=document.getElementById('draftStatus');
 draftRequest=draftRequest.catch(()=>{}).then(async()=>{try{const response=await fetch(form.dataset.draftUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.message||'Chưa lưu được nháp. Giữ trang đang mở và thử lại.');box.textContent='Đã lưu nháp lúc '+new Date(result.saved_at).toLocaleTimeString('vi-VN');}catch(error){box.textContent=error.message;draftDirty=true;}});
 return draftRequest;
}
form.addEventListener('input',event=>{listeningProgress();if(speaking||uploading||!(event.target.name==='text'||event.target.name.startsWith('q_')||event.target.name.startsWith('s_')))return;draftDirty=true;clearTimeout(draftTimer);draftTimer=setTimeout(saveDraft,800);});
window.addEventListener('beforeunload',event=>{if(!uploading&&(draftDirty||(speaking&&(blob||recording?.state==='recording')))){event.preventDefault();event.returnValue='';}});
function releaseStream(){if(stream){stream.getTracks().forEach(track=>track.stop());stream=null;}}
function updateButtons(){if(!start)return;start.disabled=requesting||uploading||!!(recording&&recording.state!=='inactive');stop.disabled=!recording||recording.state!=='recording';submitButton.disabled=uploading||requesting||!blob||!!(recording&&recording.state!=='inactive');}
if(start)start.onclick=async()=>{
 if(requesting||uploading||(recording&&recording.state!=='inactive'))return;
 requesting=true;updateButtons();recordStatus.textContent='Đang xin quyền micro…';
 try{
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('Trình duyệt chưa hỗ trợ ghi âm. Hãy dùng Chrome/Edge/Firefox/Safari mới trên HTTPS hoặc localhost.');
  stream=await navigator.mediaDevices.getUserMedia({audio:true,video:false});
  if(disposed){releaseStream();return;}
  const type=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(value=>MediaRecorder.isTypeSupported(value));
  if(!type)throw Error('Trình duyệt không có định dạng ghi âm được hỗ trợ. Hãy dùng trình duyệt khác.');
  recording=new MediaRecorder(stream,{mimeType:type});
  let chunks=[],size=0,failed=false;
  blob=null;if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null;}preview.pause();preview.removeAttribute('src');preview.hidden=true;
  recording.ondataavailable=event=>{if(event.data.size){size+=event.data.size;chunks.push(event.data);if(size>maxBytes){failed=true;recordStatus.textContent='Bản ghi vượt 20 MiB. Hãy ghi lại ngắn hơn.';if(recording.state!=='inactive')recording.stop();}}};
  recording.onerror=()=>{failed=true;recordStatus.textContent='Ghi âm bị lỗi. Hãy kiểm tra micro và ghi lại.';releaseStream();if(recording.state!=='inactive')recording.stop();updateButtons();};
  recording.onstop=()=>{releaseStream();if(!disposed&&!failed&&size>0&&size<=maxBytes){blob=new Blob(chunks,{type});previewURL=URL.createObjectURL(blob);preview.src=previewURL;preview.hidden=false;start.textContent='Ghi lại';recordStatus.textContent='Đã có bản ghi. Nghe lại trước khi nộp.';}else{blob=null;if(!failed&&!disposed)recordStatus.textContent='Bản ghi rỗng. Hãy ghi lại.';}chunks=[];updateButtons();};
  recording.start(1000);recordStatus.textContent='Đang ghi âm — hãy đọc lại đoạn mẫu rồi bấm Dừng ghi âm.';
 }catch(error){releaseStream();recordStatus.textContent=error.name==='NotAllowedError'?'Bạn chưa cho phép dùng micro. Hãy cấp quyền rồi thử lại.':error.message;}
 finally{requesting=false;updateButtons();}
};
if(stop)stop.onclick=()=>{if(recording?.state==='recording'){recordStatus.textContent='Đang hoàn tất bản ghi…';recording.stop();updateButtons();}};
window.addEventListener('pagehide',()=>{disposed=true;if(recording&&recording.state!=='inactive')recording.stop();releaseStream();if(previewURL)URL.revokeObjectURL(previewURL);});
form.onsubmit=async event=>{
 event.preventDefault();if(uploading)return;
 if(speaking&&(!blob||requesting||(recording&&recording.state!=='inactive'))){statusBox.textContent='Bạn phải hoàn tất ghi âm trước khi nộp.';return;}
 clearTimeout(draftTimer);const pendingDraft=saveDraft();uploading=true;submitButton.disabled=true;updateButtons();statusBox.textContent='Đang gửi bài…';await pendingDraft;
 try{
  const data=new FormData(form),answers=collectAnswers(data);
  const images=data.getAll('images').filter(file=>file.size);if(images.length>5||images.some(file=>file.size>8*1024*1024))throw Error('Tối đa 5 ảnh, mỗi ảnh không quá 8 MiB.');
  data.set('answers',JSON.stringify(answers));
  if(speaking){data.delete('text');const type=blob.type.split(';')[0];const extension=type==='audio/mp4'?'mp4':type==='audio/ogg'?'ogg':'webm';data.set('audio',blob,'recording.'+extension);}
  const response=await fetch(form.dataset.submitUrl,{method:'POST',body:data,headers:{'X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value}});
  const job=await response.json();if(!response.ok)throw Error(job.message||'Không gửi được bài. Kiểm tra đăng nhập và dữ liệu.');location.href=job.detail_url;
 }catch(error){statusBox.textContent=error.message;uploading=false;submitButton.disabled=false;updateButtons();}
};
if(!speaking)submitButton.disabled=false;
listeningProgress();
})();
