'use strict';
(()=>{
const el=id=>document.getElementById(id),form=el('filters');if(!form)return;
const params=new URLSearchParams(location.search);let timer=null,controller=null;
const labels={not_submitted:'Chưa làm',in_progress:'Đang làm · chưa nộp',queued:'Đã nộp · chờ chấm',processing:'Đã nộp · chờ chấm',ai_reviewed:'Chờ giáo viên chấm',manual:'Chờ giáo viên chấm',graded:'Đã chấm',complete:'Hoàn thành',incomplete:'Bài làm bị thiếu',assessed:'Đã chấm · cần xác nhận hoàn thành',exempt:'Được miễn',exemption_pending:'Chờ duyệt miễn',locked:'Chưa mở',closed:'Đã đóng'};
function cell(row,value){const td=document.createElement('td');td.textContent=value??'—';row.append(td);return td;}
function link(row,url,label){const a=document.createElement('a');a.href=url;a.textContent=label;cell(row,'').append(a);}
function badge(row,value,label){const span=document.createElement('span');span.className='badge '+value;span.textContent=label||labels[value]||value;cell(row,'').append(span);}
function note(td,text){const small=document.createElement('small');small.textContent=text;small.style.display='block';td.append(small);}
function rows(id,data,draw,empty){const body=el(id);if(!body)return;body.replaceChildren();if(!data.length){const tr=document.createElement('tr');cell(tr,empty).colSpan=body.closest('table').querySelectorAll('th').length;tr.firstChild.className='empty';body.append(tr);}for(const item of data){const tr=document.createElement('tr');draw(tr,item);body.append(tr);}}
function pager(id,info,key){const box=el(id);if(!box)return;box.replaceChildren();if(info.pages<=1)return;const prev=document.createElement('button'),next=document.createElement('button'),label=document.createElement('span');prev.type=next.type='button';prev.textContent='← Trước';next.textContent='Sau →';prev.disabled=info.page<=1;next.disabled=info.page>=info.pages;prev.className=next.className='btn secondary small';label.textContent='Trang '+info.page+'/'+info.pages+' · '+info.total+' kết quả';prev.onclick=()=>{params.set(key,info.page-1);refresh();};next.onclick=()=>{params.set(key,info.page+1);refresh();};box.append(prev,label,next);}
for(const field of form.elements)if(field.name&&params.has(field.name))field.value=params.get(field.name);
form.onsubmit=event=>{event.preventDefault();for(const key of ['classroom','skill','scope','q','date_from','date_to'])params.delete(key);for(const [key,value]of new FormData(form))if(value)params.set(key,value);for(const key of [...params.keys()])if(key.endsWith('_page'))params.delete(key);refresh();};
async function refresh(){
 clearTimeout(timer);controller?.abort();const active=new AbortController();controller=active;
 try{
  const response=await fetch('/dashboard/metrics/?'+params,{cache:'no-store',signal:active.signal});
  if(response.status===401){el('reportStatus').textContent='Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại để xem báo cáo.';return;}
  if(!response.ok)throw Error(response.status===400?'Bộ lọc chưa hợp lệ. Kiểm tra lại khoảng ngày.':'Chưa tải được báo cáo. Dữ liệu hiển thị có thể đã cũ.');
  const d=await response.json(),student=d.role==='student';
  el('rate').textContent=d.completion_rate+'%';
  el('counts').textContent=d.completed_count+'/'+d.assigned_count+' bài hoàn thành · '+d.submitted_count+' bài đã nộp';
  if(el('score'))el('score').textContent=d.average_score??'—';
  el('fourth').textContent=student?d.assigned_count-d.completed_count:d.review_queue_count;
  el('scope').textContent=student?'Chưa hoàn thành trong phạm vi lọc':d.learner_count+' học viên · '+d.on_time_completed_count+' bài hoàn thành đúng hạn';
  el('exemptCount').textContent=d.exempt_count+' bài được miễn · '+d.exemption_pending_count+' đơn chờ duyệt';
  rows('risks',d.at_risk_learners,(r,x)=>{cell(r,x.learner_name);cell(r,x.missed_tasks);cell(r,(x.reason==='missed_tasks'?'Nhiều bài quá hạn chưa hoàn thành':'Ít hoạt động và còn bài quá hạn')+(x.incomplete_tasks?' · '+x.incomplete_tasks+' bài đã chấm còn thiếu':''));},'Chưa có học viên thuộc diện cần hỗ trợ.');
  rows('queue',d.review_queue,(r,x)=>{cell(r,x.title);cell(r,x.learner_name);badge(r,x.status,x.review_status_label);link(r,x.detail_url,d.role==='manager'?'Xem bài nộp →':'Chấm / xác nhận →');},'Các bài cần chấm đã được xử lý.');
  rows('progress',d.learner_progress,(r,x)=>{[x.learner_name,x.assigned,x.completed,x.incomplete,x.not_submitted,x.in_progress,x.awaiting_grade,x.completion_pending,x.exempt,x.completion_rate+'%',x.average_score].forEach(v=>cell(r,v));},'Chưa có học viên được giao bài trong phạm vi lọc.');
  rows('grades',d.graded_report,(r,x)=>{note(cell(r,x.title),x.status_label);[x.learner_name,x.final_score,x.teacher_feedback].forEach(v=>cell(r,v));link(r,x.detail_url,'Xem chi tiết');},'Chưa có điểm cuối cùng trong phạm vi lọc.');
  rows('tasks',d.tasks,(r,x)=>{
   cell(r,x.title);cell(r,x.classroom);if(!student)cell(r,x.learner_name);
   const due=cell(r,new Date(x.due_at).toLocaleString('vi-VN'));
   if(x.is_late)note(due,x.processing_status&&x.processing_status!=='graded'?'Đến hạn · chờ xác nhận hoàn thành':'Quá hạn chưa hoàn thành');
   badge(r,x.latest_status);if(x.resubmission_pending)note(r.lastChild,'Lần nộp mới đang chờ chấm');
   cell(r,x.final_score);
   if(student){if(x.submit_url)link(r,x.submit_url,x.blocked_reason?'Xem yêu cầu':x.latest_status==='not_submitted'?'Làm bài →':'Xem / nộp lại');else if(x.result_url)link(r,x.result_url,'Xem kết quả');else cell(r,'Bài lịch sử');}
  },'Chưa có bài tập phù hợp với bộ lọc.');
  rows('history',d.history,(r,x)=>{cell(r,x.title);cell(r,new Date(x.submitted_at).toLocaleString('vi-VN'));badge(r,x.status==='graded'?x.completion_status:x.status,x.status_label);cell(r,x.final_score);link(r,x.detail_url,'Xem nhận xét →');},'Bạn chưa nộp bài trong phạm vi lọc.');
  for(const[id,key,info]of [['tasksPager','tasks_page',d.tasks_pagination],['queuePager','queue_page',d.queue_pagination],['progressPager','progress_page',d.progress_pagination],['gradesPager','grades_page',d.grades_pagination],['historyPager','history_page',d.history_pagination]])pager(id,info,key);
  el('exportLink').href='/dashboard/export/?'+params;el('reportStatus').textContent='Cập nhật '+new Date(d.updated_at).toLocaleTimeString('vi-VN')+' · tự cập nhật mỗi 10 giây';history.replaceState(null,'','?'+params);
 }catch(error){if(error.name!=='AbortError')el('reportStatus').textContent=error.message;}
 finally{if(active===controller)timer=setTimeout(refresh,10000);}
}
window.addEventListener('pagehide',()=>{clearTimeout(timer);controller?.abort();controller=null;});
refresh();
})();
