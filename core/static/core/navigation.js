'use strict';
(()=>{
 const side=document.getElementById('sidebarMenu');if(!side)return;
 const root=document.documentElement,body=document.body;
 const toggles=[...document.querySelectorAll('[data-menu-toggle]')];
 const closers=[...document.querySelectorAll('[data-menu-close]')];
 const shade=document.querySelector('.sidebar-shade');
 const mobile=window.matchMedia('(max-width:991px)');
 let lastToggle=toggles[0];
 const workspaces=[...document.querySelectorAll('.app-main,.learning-workspace')];
 const accounts=[...document.querySelectorAll('.topbar-account')];
 let measuredWidth=0,widthFrame=0;
 const observeWidth=()=>{const width=Math.round(workspaces[0]?.getBoundingClientRect().width||innerWidth);if(width===measuredWidth)return;measuredWidth=width;root.classList.toggle('workspace-compact',width<960);root.classList.toggle('workspace-tight',width<680);};
 if(workspaces[0])new ResizeObserver(()=>{if(!widthFrame)widthFrame=requestAnimationFrame(()=>{widthFrame=0;observeWidth();});}).observe(workspaces[0]);
 document.addEventListener('click',event=>accounts.forEach(account=>{if(!account.contains(event.target))account.open=false;}));
 const isOpen=()=>mobile.matches?root.classList.contains('sidebar-open'):!root.classList.contains('sidebar-collapsed');
 function sync(){
  const open=isOpen(),modal=mobile.matches&&open;
  side.inert=!open;side.setAttribute('aria-hidden',String(!open));
  toggles.forEach(button=>{button.setAttribute('aria-expanded',String(open));button.setAttribute('aria-label',open?'Đóng điều hướng':'Mở điều hướng');});
  if(shade)shade.hidden=!modal;
  body.style.overflow=modal?'hidden':'';
  workspaces.forEach(workspace=>workspace.inert=modal);
  if(modal){side.setAttribute('role','dialog');side.setAttribute('aria-modal','true');}
  else{side.removeAttribute('role');side.removeAttribute('aria-modal');}
 }
 function setOpen(open,remember=true){
  accounts.forEach(account=>account.open=false);
  if(mobile.matches)root.classList.toggle('sidebar-open',open);
  else{
   root.classList.toggle('sidebar-collapsed',!open);
   if(remember)try{localStorage.setItem('mrbean.sidebar.closed',open?'0':'1');}catch(e){}
  }
  sync();
 }
 function close(){setOpen(false);lastToggle?.focus();}
 toggles.forEach(button=>button.addEventListener('click',()=>{lastToggle=button;setOpen(!isOpen());if(mobile.matches&&isOpen())side.querySelector('[data-menu-close]')?.focus();}));
 closers.forEach(button=>button.addEventListener('click',close));
 shade?.addEventListener('click',close);
 side.querySelectorAll('.sidebar-menu-item.active>a').forEach(a=>a.setAttribute('aria-current','page'));
 side.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{if(mobile.matches)setOpen(false,false);}));
 document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&accounts.some(account=>account.open)){accounts.forEach(account=>{if(account.open){account.open=false;account.querySelector('summary')?.focus();}});return;}
  if(event.key==='Escape'&&isOpen()&&(mobile.matches||side.contains(document.activeElement))&&!document.querySelector('[role="dialog"]:not(#sidebarMenu):not(.hidden)')){close();return;}
  if(event.key!=='Tab'||!mobile.matches||!isOpen())return;
  const items=[...side.querySelectorAll('a[href],button:not([disabled])')].filter(el=>el.getClientRects().length);
  if(!items.length)return;
  if(event.shiftKey&&document.activeElement===items[0]){event.preventDefault();items.at(-1).focus();}
  else if(!event.shiftKey&&document.activeElement===items.at(-1)){event.preventDefault();items[0].focus();}
 });
 mobile.addEventListener('change',()=>{root.classList.remove('sidebar-open');sync();});
 window.addEventListener('storage',event=>{if(event.key==='mrbean.sidebar.closed'){root.classList.toggle('sidebar-collapsed',event.newValue==='1');sync();}});
 sync();
 observeWidth();
})();
