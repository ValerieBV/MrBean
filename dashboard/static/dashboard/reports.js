(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('learning-report');
  if (!root) return;
  const form = $('filters'), staff = root.dataset.staff === '1', overview = !!$('progress');
  const dimensions = ['classroom', 'skill', 'stage', 'focus', 'date_from', 'date_to', 'week', 'scope', 'q', ...(staff ? ['ai'] : [])];
  const pages = {tasks:'tasksPager', history:'historyPager', progress:'progressPager', risks:'risksPager',
    queue:'queuePager', support:'supportPager'};
  const pageKeys = Object.keys(pages).map(k => k + '_page');
  const labels = {classroom:'Lớp', skill:'Kỹ năng', stage:'Trạng thái', focus:'Nhóm', ai:'AI', week:'Tuần từ',
    date_from:'Giao từ', date_to:'Giao đến', scope:'Phạm vi', q:'Tìm'};
  const empty = txt => node('p', txt, 'lr-empty');
  const percent = n => new Intl.NumberFormat('vi-VN', {maximumFractionDigits:2}).format(n)+'%';
  const dateTime = iso => new Date(iso).toLocaleString('vi-VN', {dateStyle:'short', timeStyle:'short'});
  const localDay = iso => iso.split('-').reverse().join('/');
  function node(tag, text, className) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  function link(text, href, className) {
    const a = node('a', text, className); a.href = href; return a;
  }
  function text(id, value) { const el = $(id); if (el) el.textContent = value; }
  function clean(raw, keys) {
    const p = new URLSearchParams();
    for (const k of keys) { const v = raw.get(k); if (v && !(k==='scope' && v==='live')) p.set(k, v); }
    return p;
  }
  function localUrl(path, p) { const query = p.toString(); return path+(query ? '?'+query : ''); }
  function drill(path) {
    const p = clean(params, dimensions);
    const back = clean(params, [...dimensions, ...pageKeys]).toString();
    if (back) p.set('back', back);
    return localUrl(path, p);
  }
  function getState() {
    const raw = new URLSearchParams(location.search);
    return clean(raw, [...dimensions, ...pageKeys, ...($('backOverview') ? ['back'] : [])]);
  }
  let params = getState(), controller, lastPayload = '', searchTimer, refreshTimer, active = true;
  function reflect() {
    for (const key of dimensions) {
      const control = form.elements.namedItem(key);
      if (control) control.value = params.get(key) || '';
    }
    if (['focus','scope','ai'].some(k=>params.has(k))) $('extraFilters').open = true;
    const chips = [];
    for (const k of dimensions) {
      if (!params.has(k)) continue;
      const v = params.get(k), ctrl = form.elements.namedItem(k);
      const display = ctrl?.selectedOptions?.[0]?.textContent || (['week','date_from','date_to'].includes(k) ? localDay(v) : v);
      const chip = node('button', labels[k]+': '+display+' ×');
      chip.type='button'; chip.dataset.remove=k; chip.setAttribute('aria-label','Bỏ bộ lọc '+labels[k]+': '+display);
      chips.push(chip);
    }
    $('filterChips').replaceChildren(...chips);
    $('exportLink').href = localUrl(root.dataset.export, clean(params, dimensions));
    if ($('backOverview')) $('backOverview').href=localUrl(root.dataset.overview,
      clean(new URLSearchParams(params.get('back') || ''), [...dimensions, ...pageKeys]));
  }
  function change(next) {
    clearTimeout(searchTimer);
    if (next.toString() === params.toString()) return load(true);
    params=next;
    window.history.pushState(null,'',localUrl(location.pathname,params)+location.hash);
    reflect(); load(true);
  }
  function slice(key,value,toggle=true) {
    const next = new URLSearchParams(params);
    for (const name of pageKeys) next.delete(name);
    if (!value || (toggle && next.get(key)===value)) next.delete(key); else next.set(key,value);
    change(next);
  }
  function applyForm() {
    if (!form.reportValidity()) return;
    const next=clean(new URLSearchParams(new FormData(form)),dimensions);
    for (const k of ['week','back']) if (params.has(k)) next.set(k,params.get(k));
    change(next);
  }
  function validateDates() {
    const from=form.elements.date_from, to=form.elements.date_to;
    to.setCustomValidity(from.value && to.value && from.value>to.value ? 'Ngày kết thúc phải từ ngày bắt đầu trở đi.' : '');
  }
  form.addEventListener('submit',e=>{e.preventDefault(); validateDates(); applyForm();});
  form.addEventListener('change', e=>{if (e.target.name!=='q') {validateDates();applyForm();}});
  form.elements.q.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(applyForm,350);});
  $('resetFilters').addEventListener('click',()=>{
    form.elements.date_to.setCustomValidity('');
    change(clean(params,['back']));
  });
  $('retry').addEventListener('click',()=>load(true));
  root.addEventListener('click',e=>{
    const b=e.target.closest('button'); if (!b || !root.contains(b)) return;
    if (b.dataset.key) slice(b.dataset.key,b.dataset.value);
    else if (b.dataset.remove) slice(b.dataset.remove,'');
    else if (b.dataset.page) {
      const next = new URLSearchParams(params), key=b.dataset.page+'_page';
      if (b.dataset.number==='1') next.delete(key); else next.set(key,b.dataset.number);
      change(next);
    }
  });
  window.addEventListener('popstate',()=>{clearTimeout(searchTimer);params=getState();reflect();validateDates();load(true);});

  function filterButton(key, value, name) {
    const b=node('button'); b.type='button';b.dataset.key=key;b.dataset.value=value;
    b.setAttribute('aria-label',name);b.setAttribute('aria-pressed',String(params.get(key)===value));return b;
  }
  function bar(width) {
    const track=node('span',null,'lr-track'), value=node('i');
    value.style.width=Math.max(0,Math.min(100,width))+'%';track.setAttribute('aria-hidden','true');
    track.append(value);return track;
  }
  function chart(id, items, key, frequency=false) {
    if (!$(id)) return;
    const total=items.reduce((sum,x)=>sum+x.total,0);
    const buttons=items.map(x=>{
      const ratio=frequency ? x.total*100/total : x.assigned ? x.completed*100/x.assigned : 0;
      const stat=frequency ? String(x.total) : x.assigned ? x.completed+'/'+x.assigned+' · '+percent(ratio) : 'Được miễn';
      const b=filterButton(key,x.key,'Lọc '+x.label+' · '+stat);
      b.append(node('span',x.label),node('b',stat),bar(ratio));return b;
    });
    $(id).replaceChildren(...(buttons.length?buttons:[empty('Không có lượt giao trong phạm vi này.')]));
  }
  function weekly(items) {
    const max=Math.max(1,...items.map(x=>x.assigned));
    $('weekChart').replaceChildren(...(items.length ? [...items].reverse().map(x=>{
      const when=localDay(x.key), b=filterButton('week',x.key,'Tuần từ '+when+': '+x.completed+'/'+x.assigned+' lượt hoàn thành');
      b.className='lr-week';
      const pair=node('span',null,'lr-week-pair');pair.setAttribute('aria-hidden','true');
      for (const n of [x.assigned,x.completed]) {const s=node('i');s.style.height=(100*n/max)+'%';pair.append(s);}
      b.append(pair,node('b',x.completed+'/'+x.assigned),node('small',when));return b;
    }) : [empty('Chưa có tuần giao bài trong phạm vi này.')]));
  }
  function person(code,url) {return url && overview ? link(code,drill(url),'lr-person') : node('strong',code);}
  function row(primary, secondary, action) {
    const el=node('div',null,'lr-row'), body=node('div');body.append(primary);
    if (secondary) body.append(node('small',secondary));
    el.append(body);if(action) el.append(action);return el;
  }
  function list(id, items, format, message) {
    if ($(id)) $(id).replaceChildren(...(items.length ? items.map(format) : [empty(message)]));
  }
  function task(r) {
    const parts=r.exercise_count ? 'Đã nộp '+r.submitted_exercise_count+'/'+r.exercise_count+' bài nghe' : '';
    const stage=form.elements.stage.querySelector('option[value="'+r.stage+'"]')?.textContent || r.stage;
    const summary=[r.classroom,stage,parts,(r.is_late?'Quá hạn: ':'Hạn: ')+dateTime(r.due_at)];
    if (r.resubmission_pending && r.completion_status==='complete') summary.push('Lần trước đã hoàn thành');
    if (r.blocked_reason && !r.resubmission_pending) summary.push(r.blocked_reason);
    const el=row(node('strong',r.title),summary.filter(Boolean).join(' · '),r.action_url ? link(r.action_label,r.action_url) : null);
    if(overview && r.learner_url) el.firstChild.prepend(person(r.student_code,r.learner_url));
    return el;
  }
  function pager(key, info) {
    const nav=$(pages[key]);if (!nav) return;
    nav.replaceChildren();if (!info || info.pages<2) return;
    const button=(number,label,disabled)=>{
      const b=node('button',label);b.type='button';b.disabled=disabled;b.dataset.page=key;b.dataset.number=String(number);return b;
    };
    nav.append(button(info.page-1,'Trước',info.page===1),node('span','Trang '+info.page+'/'+info.pages),
      button(info.page+1,'Sau',info.page===info.pages));
  }
  function priority(d, classes) {
    if (!overview) return;
    let title, message, action;
    const filter=(key,val,caption)=>{const b=filterButton(key,val,caption);b.className='lr-button';b.textContent=caption;return b;};
    const manual=d.ai_operations?.groups.find(x=>x.key==='manual')?.total || 0;
    const weakest=classes.find(c=>c.assigned && c.completed<c.assigned);
    if (root.dataset.role==='admin' && manual && !params.has('ai')) {
      title=manual+' bài đã chuyển sang chấm thủ công';
      message='Xem các lần nộp mà hệ thống không đưa ra được đề xuất.';
      action=filter('ai','manual','Lọc bài chấm thủ công');
    } else if (root.dataset.role==='manager' && weakest && !params.has('classroom')) {
      title='Theo sát lớp '+weakest.label;
      message=weakest.completed+'/'+weakest.assigned+' lượt hoàn thành · '+weakest.overdue+' lượt quá hạn.';
      action=filter('classroom',weakest.key,'Xem riêng lớp này');
    } else if (d.review_queue_count) {
      title=d.review_queue_count+' bài đang chờ giáo viên';
      message='Danh sách chờ xếp theo lần nộp sớm nhất cần xử lý.';
      action=link('Xem danh sách chờ','#grading-queue','lr-button');
    } else if (d.support_count) {
      title=d.support_count+' câu hỏi đang chờ phản hồi';message='Mở trao đổi để xem câu hỏi về bài của học viên.';
      action=link('Xem câu hỏi','#questions','lr-button');
    } else if (d.risk_count) {
      title=d.risk_count+' học viên cần hỗ trợ';message='Mở hồ sơ tiến độ để xác định bài đang bị chậm.';
      action=link('Xem học viên','#risk-list','lr-button');
    } else {
      title=d.assigned_count?'Không có việc chờ xử lý trong phạm vi này':'Chưa có lượt phải làm trong phạm vi này';
      message='Có thể tra cứu tiến độ từng học viên bằng mã.';action=link('Tra cứu học viên','#learners','lr-button');
    }
    text('priorityTitle',title);text('priorityText',message);$('priorityAction').replaceChildren(action);
  }
  function render(d) {
    text('rate',d.assigned_count ? percent(d.completion_rate) : 'Chưa có bài');
    text('counts',d.completed_count+'/'+d.assigned_count+' lượt phải làm · '+d.on_time_completed_count+' đúng hạn');
    text('submissionRate',d.assigned_count ? percent(d.submission_rate) : 'Chưa có bài');
    text('submissionCounts',d.submitted_count+'/'+d.assigned_count+' đã nộp · '+d.full_count+' đã nộp đủ các phần');
    text('reviewCount',d.charts.stage.find(x=>x.key==='review')?.total || 0);
    text('workCount',overview ? d.overdue_count : d.action_count);
    text('riskBadge',d.risk_count);text('supportBadge',d.support_count);
    for (const b of root.querySelectorAll('.lr-kpi')) b.setAttribute('aria-pressed',String(params.get(b.dataset.key)===b.dataset.value));
    chart('skillChart',d.charts.skill,'skill');
    chart('stageChart',d.charts.stage,'stage',true);
    const classes=[...d.charts.classroom].sort((a,b)=>(a.assigned?a.completed/a.assigned:2)-(b.assigned?b.completed/b.assigned:2) || a.label.localeCompare(b.label));
    chart('classChart',classes,'classroom');priority(d,classes);
    weekly(d.charts.week);
    if (staff && d.ai_operations) {
      const ai=d.ai_operations;
      text('aiRate',ai.timely_rate===null ? 'Chưa có số liệu' : percent(ai.timely_rate)+' đúng hạn');
      text('aiSummary',ai.total+' lần nộp hiện tại · Đề xuất trong '+ai.deadline_minutes+' phút: '+
        (ai.groups.find(x=>x.key==='timely')?.total || 0)+'/'+ai.measured+' lần đã biết kết quả xử lý. Không tính lần đang chờ hoặc thiếu mốc thời gian.');
      chart('aiChart',ai.groups,'ai',true);
    }
    list('risks',d.at_risk_learners,r=>row(person(r.student_code,r.detail_url),
      r.missed_tasks+' bài quá hạn · '+(r.reason==='inactive'?'Ít hoạt động':'Nhiều bài chưa hoàn thành'),
      link('Xem tiến độ',drill(r.detail_url))), 'Không có học viên chạm ngưỡng hỗ trợ trong phạm vi này.');
    list('progress',d.learner_progress,r=>{
      const el=row(person(r.student_code,r.detail_url),r.assigned ? r.completed+'/'+r.assigned+' hoàn thành · '+r.overdue+' quá hạn' : 'Chưa có lượt phải làm',
        r.detail_url ? link('Xem tiến độ',drill(r.detail_url)) : null);
      if(r.assigned) el.firstChild.append(bar(r.completion_rate));return el;
    },'Không có học viên phù hợp.');
    list('queue',d.review_queue,r=>row(person(r.student_code,r.learner_url),r.title+' · '+r.review_status_label+' · Nộp '+dateTime(r.submitted_at),
      link(root.dataset.canConfirm==='1'?'Mở để chấm':'Xem bài nộp',r.detail_url)),'Không có lần nộp nào đang chờ giáo viên.');
    list('support',d.support_queue || [],r=>row(person(r.student_code,r.learner_url),r.title+(r.since?' · Chờ từ '+dateTime(r.since):''),link('Mở trao đổi',r.detail_url)),
      'Không có câu hỏi về bài tập đang chờ bạn phản hồi.');
    list('nextTasks',d.next_tasks,task,'Không còn bài có thể làm ngay trong phạm vi này.');
    text('taskSummary',d.task_count+' lượt giao · '+d.exempt_count+' được miễn');
    list('tasks',d.tasks,task,'Không có lượt giao phù hợp với bộ lọc.');
    list('history',d.history,r=>{
      const el=row(node('strong',r.title),[dateTime(r.submitted_at),r.status_label,r.teacher_feedback].filter(Boolean).join(' · '),
        link(r.status==='graded'?'Xem kết quả':'Xem bài nộp',r.detail_url));
      if(overview) el.firstChild.prepend(person(r.student_code,r.learner_url));
      return el;
    },'Chưa có lần nộp nào trong phạm vi này.');
    for (const key of Object.keys(pages)) pager(key,d[key+'_pagination']);
  }
  async function load(interactive=false) {
    if (!active) return;
    clearTimeout(refreshTimer);controller?.abort();
    const mine=new AbortController();controller=mine;
    const body=$('reportBody');
    if(interactive) {body.setAttribute('aria-busy','true');text('reportStatus','Đang cập nhật theo bộ lọc…');}
    try {
      const url=localUrl(root.dataset.metrics,clean(params,[...dimensions,...pageKeys]));
      const response=await fetch(url,{signal:mine.signal,headers:{Accept:'application/json'},cache:'no-store'});
      if (!response.ok) throw Error(response.status===401?'Phiên đăng nhập đã hết. Hãy đăng nhập lại.':response.status===400?'Bộ lọc không hợp lệ. Hãy đổi ngày hoặc xóa bộ lọc.':'Không thể tải báo cáo.');
      const d=await response.json();
      if(controller!==mine) return;
      const stamp=JSON.stringify({...d,updated_at:null});
      if (interactive || stamp!==lastPayload || body.hidden) {
        const focus=document.activeElement;
        const keep=focus?.matches('button[data-key],button[data-page],button[data-remove]') && root.contains(focus) ? {...focus.dataset} : null;
        render(d);lastPayload=stamp;
        if (keep && !focus.isConnected) {
          const buttons=[...root.querySelectorAll('button')];
          const next=buttons.find(b=>Object.keys(keep).every(k=>b.dataset[k]===keep[k]) && !b.disabled);
          (next || $('resetFilters')).focus({preventScroll:true});
        }
      }
      body.hidden=false;
      $('reportMessage').classList.remove('is-error');$('retry').hidden=true;
      text('reportStatus','Cập nhật '+new Date(d.updated_at).toLocaleTimeString('vi-VN')+' · Chọn một cột biểu đồ hoặc thẻ chỉ số để lọc toàn trang.');
    } catch(error) {
      if(error.name==='AbortError' || controller!==mine) return;
      body.hidden=true;lastPayload='';$('retry').hidden=false;$('reportMessage').classList.add('is-error');
      text('reportStatus',error.message==='Failed to fetch'?'Không kết nối được máy chủ.':error.message);
    } finally {
      if(controller===mine) {
        body.setAttribute('aria-busy','false');
        if(active && !document.hidden) refreshTimer=setTimeout(()=>load(),60000);
      }
    }
  }
  document.addEventListener('visibilitychange',()=>{clearTimeout(refreshTimer);if(!document.hidden && active) load();});
  window.addEventListener('pagehide',()=>{active=false;clearTimeout(refreshTimer);clearTimeout(searchTimer);controller?.abort();});
  window.addEventListener('pageshow',e=>{if(e.persisted){active=true;params=getState();reflect();load(true);}});
  reflect();load();
})();
