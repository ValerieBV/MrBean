'use strict';
(()=>{
 let sequence=0;
 const clock=value=>{const seconds=Math.max(0,Math.floor(value)),m=Math.floor(seconds/60),s=seconds%60;return m+':'+String(s).padStart(2,'0');};
 document.querySelectorAll('audio[controls]').forEach(audio=>{
  const tools=document.createElement('div');tools.className='audio-tools';tools.setAttribute('role','group');tools.setAttribute('aria-label','Điều khiển nghe lại');
  const state=document.createElement('p');state.className='audio-seek-status';state.setAttribute('role','status');
  function button(label,handler){const node=document.createElement('button');node.type='button';node.textContent=label;node.onclick=handler;tools.append(node);return node;}
  const duration=()=>{if(Number.isFinite(audio.duration)&&audio.duration>0)return audio.duration;for(const ranges of [audio.seekable,audio.buffered]){if(ranges.length){const end=ranges.end(ranges.length-1);if(Number.isFinite(end)&&end>0)return end;}}return 0;};
  function seek(target,play=false){
   if(!duration()){state.textContent='Chờ tải thông tin file nghe để chọn vị trí.';return;}
   audio.currentTime=Math.max(0,Math.min(duration(),target));state.textContent='Vị trí nghe '+clock(audio.currentTime)+' / '+clock(duration());
   if(play)audio.play().catch(()=>{state.textContent='Đã chọn vị trí. Bấm phát để tiếp tục nghe.';});
  }
  button('↶ Lùi 10 giây',()=>seek(audio.currentTime-10));
  button('Tiến 10 giây ↷',()=>seek(audio.currentTime+10));
  button('Nghe từ đầu',()=>seek(0,true));
  const jump=document.createElement('div');jump.className='audio-jump';
  const label=document.createElement('label'),input=document.createElement('input'),go=document.createElement('button');
  input.id='audio-jump-'+(++sequence);input.type='text';input.inputMode='numeric';input.placeholder='02:30';input.maxLength=9;input.autocomplete='off';
  label.htmlFor=input.id;label.textContent='Nghe tại mốc';go.type='button';go.textContent='Đi đến';
  function jumpTo(){
   const value=input.value.trim();if(!/^\d{1,3}:\d{2}(?::\d{2})?$/.test(value)){state.textContent='Nhập phút:giây, ví dụ 02:30.';return;}
   const parts=value.split(':').map(Number);if(parts.at(-1)>=60||(parts.length===3&&parts[1]>=60)){state.textContent='Phần giây và phút trong giờ phải nhỏ hơn 60.';return;}
   const target=parts.reduce((total,part)=>total*60+part,0);
   if(target>duration()){state.textContent=(Number.isFinite(audio.duration)?'File nghe dài ':'Hiện có thể chọn đến ')+clock(duration())+'. Chọn mốc trong khoảng này.';return;}
   seek(target,true);
  }
  go.onclick=jumpTo;input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();jumpTo();}});
  jump.append(label,input,go);tools.append(jump,state);audio.after(tools);
  function update(){
   tools.hidden=audio.hidden||!(audio.getAttribute('src')||audio.querySelector('source'));
   tools.querySelectorAll('button,input').forEach(node=>node.disabled=!duration());
  }
  audio.addEventListener('progress',update);audio.addEventListener('loadeddata',update);audio.addEventListener('loadedmetadata',update);audio.addEventListener('durationchange',update);audio.addEventListener('emptied',update);audio.addEventListener('error',update);
  new MutationObserver(update).observe(audio,{attributes:true,attributeFilter:['src','hidden']});update();
 });
})();
