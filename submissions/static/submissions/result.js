'use strict';
(()=>{if(document.getElementById('resultPoll')?.dataset.pending==='true')setTimeout(()=>location.reload(),10000);
const form=document.getElementById('reviewForm');if(!form)return;
form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;const state=document.getElementById('reviewStatus');state.textContent='Đang lưu điểm…';try{const response=await fetch(form.dataset.reviewUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({score:Number(form.elements.score.value),feedback:form.elements.feedback.value})});if(!response.ok)throw Error(response.status===409?'Bài đã được xác nhận. Tải lại trang để xem kết quả.':'Không lưu được điểm. Kiểm tra dữ liệu và quyền phụ trách lớp.');location.reload();}catch(error){state.textContent=error.message;button.disabled=false;}};
})();
