'use strict';
(()=>{
 if(document.getElementById('resultPoll')?.dataset.pending==='true')setTimeout(()=>location.reload(),10000);
 for(const id of ['reviewForm','completionForm']){
  const form=document.getElementById(id);if(!form)continue;
  form.onsubmit=async event=>{
   event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
   const state=document.getElementById(id==='reviewForm'?'reviewStatus':'completionStatus');state.textContent='Đang lưu kết quả…';
   const data={completion_status:form.elements.completion_status.value};
   if(id==='reviewForm'){data.score=Number(form.elements.score.value);data.feedback=form.elements.feedback.value;}
   try{const response=await fetch(form.dataset.reviewUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(data)});
    if(!response.ok)throw Error(response.status===409?'Bài đã được xác nhận. Tải lại trang để xem kết quả.':'Không lưu được kết quả. Kiểm tra dữ liệu và quyền phụ trách lớp.');
    location.reload();
   }catch(error){state.textContent=error.message;button.disabled=false;}
  };
 }
})();
