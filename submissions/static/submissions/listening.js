'use strict';
(() => {
    const form=document.getElementById('submissionForm');if(!form||form.dataset.kind!=='listening')return;
    const panels=[...form.querySelectorAll('[data-listening-exercise]')],tabs=[...document.querySelectorAll('[data-listening-tab]')];
    const indices=new Map();
    const done=question=>question.querySelector('input[type=radio]:checked')&&(question.dataset.requiresShortAnswer!=='true'||question.querySelector('.listening-answer').value.trim());
    function render(panel){
        const questions=[...panel.querySelectorAll('[data-question]')];
        const index=indices.get(panel)||0;indices.set(panel,index);
        const nav=panel.querySelector('.listening-question-nav');nav.replaceChildren();
        questions.forEach((question,i)=>{
            question.hidden=i!==index;
            const button=document.createElement('button');button.type='button';button.className='question-number'+(done(question)?' answered':'')+(i===index?' current':'');
            button.textContent=question.dataset.number;button.setAttribute('aria-label','Đến câu '+question.dataset.number);button.setAttribute('aria-pressed',String(i===index));
            button.onclick=()=>{indices.set(panel,i);render(panel);};nav.append(button);
        });
        panel.querySelector('[data-question-prev]').disabled=index===0;
        panel.querySelector('[data-question-next]').disabled=index===questions.length-1;
        panel.querySelector('.question-counter').textContent=(index+1)+' / '+questions.length;
    }
    function selectPanel(order,focus=false){
        panels.forEach(panel=>{const selected=panel.dataset.listeningExercise===String(order);panel.hidden=!selected;if(!selected)panel.querySelectorAll('audio').forEach(audio=>audio.pause());});
        tabs.forEach(tab=>{const selected=tab.dataset.listeningTab===String(order);tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;if(selected&&focus)tab.focus();});
        history.replaceState(null,'','#listening-'+order);
    }
    panels.forEach(panel=>{
        render(panel);
        panel.querySelector('[data-question-prev]').onclick=()=>{indices.set(panel,indices.get(panel)-1);render(panel);};
        panel.querySelector('[data-question-next]').onclick=()=>{indices.set(panel,indices.get(panel)+1);render(panel);};
        panel.addEventListener('input',()=>{const current=indices.get(panel);panel.querySelectorAll('.listening-question-nav button').forEach((button,i)=>button.classList.toggle('answered',Boolean(done(panel.querySelectorAll('[data-question]')[i]))));indices.set(panel,current);});
    });
    tabs.forEach((tab,index)=>{tab.onclick=()=>selectPanel(tab.dataset.listeningTab);tab.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;selectPanel(tabs[next].dataset.listeningTab,true);};});
    document.querySelectorAll('[data-pdf-toggle]').forEach(button=>button.onclick=()=>{const panel=document.getElementById(button.dataset.pdfToggle);panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));button.textContent=panel.hidden?'Xem đề PDF':'Ẩn đề PDF';});
    const requested=location.hash.match(/^#listening-(\d+)$/)?.[1];
    selectPanel(panels.some(panel=>panel.dataset.listeningExercise===requested)?requested:panels[0]?.dataset.listeningExercise);
})();
