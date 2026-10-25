'use strict';
const form=document.getElementById('submissionForm');
const statusBox=document.getElementById('submissionStatus'),submitButton=document.getElementById('submitButton');
const speaking=form.dataset.kind==='speaking';
let recording=null,stream=null,blob=null,previewURL=null,requesting=false,disposed=false,uploading=false;
const start=document.getElementById('recordStart'),stop=document.getElementById('recordStop'),preview=document.getElementById('recordPreview'),recordStatus=document.getElementById('recordStatus');
const maxBytes=20*1024*1024;
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
 uploading=true;submitButton.disabled=true;updateButtons();statusBox.textContent='Đang gửi bài…';
 try{
  const data=new FormData(form),answers={};for(const [key,value]of data)if(key.startsWith('q_'))answers[key.slice(2)]=value;
  data.set('answers',JSON.stringify(answers));
  if(speaking){data.delete('text');const type=blob.type.split(';')[0];const extension=type==='audio/mp4'?'mp4':type==='audio/ogg'?'ogg':'webm';data.set('audio',blob,'recording.'+extension);}
  const response=await fetch(form.dataset.submitUrl,{method:'POST',body:data,headers:{'X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value}});
  const job=await response.json();if(!response.ok)throw Error(job.message||'Không gửi được bài. Kiểm tra đăng nhập và dữ liệu.');location.href=job.detail_url;
 }catch(error){statusBox.textContent=error.message;uploading=false;submitButton.disabled=false;updateButtons();}
};
