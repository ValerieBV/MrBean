'use strict';
const menu=document.querySelector('[data-menu-toggle]');
const side=document.getElementById('sidebar');
const shade=document.querySelector('.sidebar-shade');
function closeMenu(){side?.classList.remove('is-open');shade?.classList.remove('is-open');menu?.setAttribute('aria-expanded','false');document.body.style.overflow='';}
menu?.addEventListener('click',()=>{const open=side.classList.toggle('is-open');shade?.classList.toggle('is-open',open);menu.setAttribute('aria-expanded',String(open));document.body.style.overflow=open?'hidden':'';if(open)side.querySelector('a')?.focus();});
shade?.addEventListener('click',()=>{closeMenu();menu?.focus();});
document.addEventListener('keydown',event=>{
 if(!side?.classList.contains('is-open'))return;
 if(event.key==='Escape'){closeMenu();menu?.focus();}
 if(event.key==='Tab'){
  const items=[...side.querySelectorAll('a[href],button:not([disabled]),summary')].filter(item=>item.getClientRects().length);items.push(menu);
  if(event.shiftKey&&document.activeElement===items[0]){event.preventDefault();items.at(-1).focus();}
  else if(!event.shiftKey&&document.activeElement===items.at(-1)){event.preventDefault();items[0].focus();}
 }
});
window.matchMedia('(min-width:992px)').addEventListener('change',event=>{if(event.matches)closeMenu();});
for(const box of document.querySelectorAll('.table-wrap,.report-scroll')){
 box.setAttribute('role','region');box.setAttribute('aria-label','Bảng dữ liệu, có thể cuộn ngang');
 const update=()=>{if(box.scrollWidth>box.clientWidth+1)box.setAttribute('tabindex','0');else box.removeAttribute('tabindex');};
 new ResizeObserver(update).observe(box);update();
}
const skillSelect=document.getElementById('id_skill');
if(skillSelect){
 const toggleFields=()=>{for(const [name,skill]of Object.entries({listening_type:'listening',audio_file:'listening',video_file:'speaking',youtube_url:'speaking',reference_transcript:'speaking'})){const box=document.querySelector('[data-field="'+name+'"]');if(box)box.hidden=skillSelect.value!==skill&&!box.dataset.hasErrors;}};
 skillSelect.addEventListener('change',toggleFields);toggleFields();
}
// The account menu follows the reference topbar and also works without Bootstrap JS.
const accountMenu=document.querySelector('.account-menu');
document.addEventListener('click',event=>{if(accountMenu?.open&&!accountMenu.contains(event.target))accountMenu.open=false;});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&accountMenu?.open){accountMenu.open=false;accountMenu.querySelector('summary').focus();}});

for(const button of document.querySelectorAll('[data-dismiss-alert]'))button.addEventListener('click',()=>button.closest('.flash-alert').remove());
