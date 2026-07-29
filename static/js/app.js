/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Horizon Video Downloader v5 — App Controller
   Tab switching · Segmented toggles · Playlist fetch + select · WS · DL Cards
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

/* ─── Icons ──────────────────────────────────────────────────── */
const IC={
  pause:'<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>',
  play:'<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21"/></svg>',
  x:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  err:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  stop:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
  folder:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  tOk:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>',
  tErr:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
  tInfo:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
};
const DONE=new Set(['completed','error','cancelled']);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function fmtDur(s){if(!s)return'';const m=Math.floor(s/60),sec=Math.floor(s%60);return`${m}:${String(sec).padStart(2,'0')}`;}

/* ─── WebSocket ──────────────────────────────────────────────── */
class WS{
  constructor(onMsg,onOpen,onClose){this._m=onMsg;this._o=onOpen;this._c=onClose;this._ws=null;this._d=1000;this._t=null;this._dead=false;}
  connect(){this._dead=false;try{this._ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);}catch{this._retry();return;}
    this._ws.onopen=()=>{this._d=1000;this._o?.();};
    this._ws.onmessage=e=>{try{this._m?.(JSON.parse(e.data));}catch{}};
    this._ws.onclose=()=>{this._c?.();if(!this._dead)this._retry();};
    this._ws.onerror=()=>{};}
  close(){this._dead=true;clearTimeout(this._t);this._ws?.close();}
  _retry(){clearTimeout(this._t);this._t=setTimeout(()=>{this._d=Math.min(this._d*1.5,30000);this.connect();},this._d);}
}

/* ─── Download Card ──────────────────────────────────────────── */
class DLCard{
  constructor(d){this.id=d.task_id;this._s='';this._dp=0;this._tp=0;this._raf=null;this.el=this._mk(d);this.update(d);}
  _mk(d){const c=document.createElement('div');c.className='dl-card glass-panel';c.dataset.taskId=this.id;c.dataset.status=d.status||'queued';
    c.innerHTML=`<div class="dl-head"><div class="dl-info"><span class="dl-name">${esc(d.filename||'Initializing…')}</span><span class="dl-meta">${d.format_type==='audio'?'Audio':'Video'}</span></div><div class="dl-actions"><button class="dl-btn pr-btn" title="Pause" type="button">${IC.pause}</button><button class="dl-btn fld-btn" title="Open Folder" type="button" style="display:none">${IC.folder}</button><button class="dl-btn x-btn" title="Cancel" type="button">${IC.x}</button></div><span class="dl-badge"></span></div><div class="dl-progress"><div class="dl-track"><div class="dl-fill"></div></div><div class="dl-stats"><span class="dl-pct">0%</span><span class="dl-spd"></span><span class="dl-eta"></span></div></div><div class="dl-err" style="display:none"></div>`;
    this.$={nm:c.querySelector('.dl-name'),act:c.querySelector('.dl-actions'),badge:c.querySelector('.dl-badge'),fill:c.querySelector('.dl-fill'),pct:c.querySelector('.dl-pct'),spd:c.querySelector('.dl-spd'),eta:c.querySelector('.dl-eta'),er:c.querySelector('.dl-err'),pr:c.querySelector('.pr-btn'),fld:c.querySelector('.fld-btn'),xb:c.querySelector('.x-btn')};
    this.$.pr.onclick=()=>this._pr();this.$.fld.onclick=()=>this._fld();this.$.xb.onclick=()=>this._cx();return c;}
  update(d){this._s=d.status;this.el.dataset.status=d.status;
    if(d.filename)this.$.nm.textContent=d.filename;
    this._tp=d.progress??this._tp;if(!this._raf)this._anim();
    this.$.pct.textContent=`${Math.round(this._tp)}%`;
    this.$.spd.textContent=d.speed||'';this.$.eta.textContent=d.eta?`ETA ${d.eta}`:'';
    if(d.status==='downloading'){this._show(true);this.$.pr.innerHTML=IC.pause;this.$.pr.title='Pause';this.$.pr.style.display='flex';this.$.xb.style.display='flex';this.$.fld.style.display='none';this.$.badge.className='dl-badge';}
    else if(d.status==='paused'){this._show(true);this.$.pr.innerHTML=IC.play;this.$.pr.title='Resume';this.$.pr.style.display='flex';this.$.xb.style.display='flex';this.$.fld.style.display='none';this._bdg('paused','Paused',IC.pause);}
    else if(d.status==='completed'){this._show(true);this.$.pr.style.display='none';this.$.xb.style.display='none';this.$.fld.style.display='flex';this.$.spd.textContent='';this.$.eta.textContent='';this._bdg('done','Done',IC.check);if(d.progress>=99)App.notify(d.filename||'File');}
    else if(d.status==='error'){this._show(false);this.$.spd.textContent='';this.$.eta.textContent='';this._bdg('err','Error',IC.err);if(d.error_message){this.$.er.textContent=d.error_message;this.$.er.style.display='block';}}
    else if(d.status==='cancelled'){this._show(false);this.$.spd.textContent='';this.$.eta.textContent='';this._bdg('stopped','Cancelled',IC.stop);}
    else if(d.status==='queued'){this.$.pct.textContent='Queued';}
    if(d.filename&&d.status)App.log(`[${d.task_id?.slice(0,8)}] ${d.status} — ${d.filename}${d.progress!=null?' ('+Math.round(d.progress)+'%)':''}${d.speed?' @ '+d.speed:''}`);}
  _anim(){const diff=this._tp-this._dp;if(Math.abs(diff)<.15){this._dp=this._tp;this._raf=null;}else{this._dp+=diff*.18;this._raf=requestAnimationFrame(()=>this._anim());}this.$.fill.style.width=`${this._dp}%`;}
  async _pr(){const ep=this._s==='paused'?'resume':'pause';try{const r=await fetch(`/api/${ep}/${this.id}`,{method:'POST'});if(!r.ok)App.toast((await r.json()).error,'err');}catch{App.toast('Network error','err');}}
  async _cx(){try{const r=await fetch(`/api/cancel/${this.id}`,{method:'POST'});if(!r.ok)App.toast((await r.json()).error,'err');}catch{App.toast('Network error','err');}}
  async _fld(){try{const r=await fetch(`/api/open-folder/${this.id}`,{method:'POST'});if(!r.ok)App.toast((await r.json()).error,'err');}catch{App.toast('Network error','err');}}
  _show(a){this.$.act.style.display=a?'flex':'none';if(!a)this.$.badge.classList.add('show');else this.$.badge.classList.remove('show');}
  _bdg(c,t,i){this.$.badge.className=`dl-badge show ${c}`;this.$.badge.innerHTML=`${i}<span>${t}</span>`;}
  get done(){return DONE.has(this._s);}
}

/* ═══════════════════ APP ═══════════════════ */
const App={
  cards:new Map(),
  ws:null,
  singleMode:'video',  // current segmented state for Single tab
  plMode:'video',       // current segmented state for Playlist action bar
  plEntries:[],         // fetched playlist data
  notified:new Set(),   // prevent duplicate desktop notifications
  themes:{
    'violet-cyan':{
      '--accent':'#8b5cf6','--accent-h':'#a78bfa','--accent-dim':'rgba(139,92,246,.12)',
      '--grad':'linear-gradient(135deg,#8b5cf6,#06b6d4)','--grad-h':'linear-gradient(90deg,#8b5cf6,#06b6d4)'
    },
    'spotify':{
      '--accent':'#1db954','--accent-h':'#1ed760','--accent-dim':'rgba(29,185,84,.12)',
      '--grad':'linear-gradient(135deg,#1db954,#191414)','--grad-h':'linear-gradient(90deg,#1db954,#1ed760)'
    },
    'crimson':{
      '--accent':'#e11d48','--accent-h':'#fb7185','--accent-dim':'rgba(225,29,72,.12)',
      '--grad':'linear-gradient(135deg,#e11d48,#be123c)','--grad-h':'linear-gradient(90deg,#e11d48,#fb7185)'
    },
    'amber':{
      '--accent':'#d97706','--accent-h':'#f59e0b','--accent-dim':'rgba(217,119,6,.12)',
      '--grad':'linear-gradient(135deg,#d97706,#b45309)','--grad-h':'linear-gradient(90deg,#d97706,#f59e0b)'
    },
    'aurora':{
      '--accent':'#78ffd6','--accent-h':'#a8ff78','--accent-dim':'rgba(120,255,214,.12)',
      '--grad':'linear-gradient(135deg,#a8ff78,#78ffd6)','--grad-h':'linear-gradient(90deg,#a8ff78,#78ffd6)'
    }
  },

  /* ── Init ────────────────────────────────────────────── */
  init(){
    this._loadPersistedSettings();
    this._bindTabs();
    this._bindSegmented('single-seg',m=>{this.singleMode=m;this._toggleSingleOpts();});
    this._bindSegmented('pl-seg',m=>{this.plMode=m;this._togglePlOpts();});
    this._bindPaste();
    this._bindSingleDL();
    this._bindPlaylist();
    this._bindSocial();
    this._bindLog();
    this._bindSettings();
    this._bindTheme();
    this._bindClipboard();
    this._connectWS();
    if(window.Notification&&Notification.permission==='default')Notification.requestPermission();
  },

  /* ── Tabs ────────────────────────────────────────────── */
  _bindTabs(){
    const btns=document.querySelectorAll('.tab-btn'),panels=document.querySelectorAll('.tab-panel');
    btns.forEach(b=>b.addEventListener('click',()=>{
      btns.forEach(x=>x.classList.remove('active'));panels.forEach(x=>x.classList.remove('active'));
      b.classList.add('active');
      const p=document.getElementById(`panel-${b.dataset.tab}`);
      if(p){p.classList.remove('active');void p.offsetWidth;p.classList.add('active');}
      if(b.dataset.tab==='history')this._loadHistory();
    }));
  },

  /* ── Segmented Controls ──────────────────────────────── */
  _bindSegmented(id,cb){
    const ctrl=document.getElementById(id);if(!ctrl)return;
    ctrl.querySelectorAll('.seg-btn').forEach(b=>b.addEventListener('click',()=>{
      ctrl.querySelectorAll('.seg-btn').forEach(x=>x.classList.remove('active'));
      b.classList.add('active');cb(b.dataset.mode);
    }));
  },

  _toggleSingleOpts(){
    const v=this.singleMode==='video';
    document.getElementById('single-video-opts').classList.toggle('hidden',!v);
    document.getElementById('single-audio-opts').classList.toggle('hidden',v);
    const label=document.querySelector('#single-dl-btn .action-label');
    label.textContent=v?'DOWNLOAD VIDEO':'EXTRACT AUDIO';
  },

  _togglePlOpts(){
    const v=this.plMode==='video';
    document.getElementById('pl-bar-video-opts').classList.toggle('hidden',!v);
    document.getElementById('pl-bar-audio-opts').classList.toggle('hidden',v);
  },

  /* ── Paste Buttons ───────────────────────────────────── */
  _bindPaste(){
    document.querySelectorAll('.paste-btn').forEach(btn=>{
      btn.addEventListener('click',async()=>{
        const target=document.getElementById(btn.dataset.target);
        if(!target)return;
        try{const t=await navigator.clipboard.readText();if(t){target.value=t.trim();target.dispatchEvent(new Event('input'));}}
        catch{this.toast('Clipboard access denied','err');}
      });
    });
  },

  _getSettings(){
    return{
      output_dir:document.getElementById('set-dir')?.value.trim()||undefined,
      cookie_file:document.getElementById('set-cookie')?.value.trim()||undefined,
    };
  },

  /* ═══════════════ SINGLE TAB DOWNLOAD ═══════════════ */
  _bindSingleDL(){
    const btn=document.getElementById('single-dl-btn');
    btn.addEventListener('click',()=>this._doSingleDL());
    document.getElementById('single-url').addEventListener('keydown',e=>{if(e.key==='Enter')this._doSingleDL();});
  },

  async _doSingleDL(){
    const url=document.getElementById('single-url').value.trim();
    if(!url){this.toast('Paste a URL first','err');return;}
    const btn=document.getElementById('single-dl-btn');
    const label=btn.querySelector('.action-label'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    const settings=this._getSettings();
    const rateLimit = document.getElementById('s-rate-limit').value || undefined;
    const startTime = document.getElementById('s-start-time').value.trim() || undefined;
    const endTime = document.getElementById('s-end-time').value.trim() || undefined;

    const body={
      url,
      format_type:this.singleMode,
      rate_limit:rateLimit,
      start_time:startTime,
      end_time:endTime,
      ...settings
    };

    if(this.singleMode==='video'){
      body.quality=document.getElementById('s-resolution').value;
      body.video_format=document.getElementById('s-vformat').value;
      body.subtitles=document.getElementById('s-subs').value;
      body.subtitle_lang=document.getElementById('s-sublang').value;
    }else{
      body.audio_format=document.getElementById('s-aformat').value;
    }

    try{
      const r=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const d=await r.json();
      if(r.ok){
        document.getElementById('single-url').value='';
        document.getElementById('s-start-time').value='';
        document.getElementById('s-end-time').value='';
        this.toast('Download started','ok');
      }
      else this.toast(d.error||'Failed','err');
    }catch{this.toast('Network error','err');}
    finally{label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  /* ═══════════════ PLAYLIST TAB ═══════════════ */
  _bindPlaylist(){
    document.getElementById('pl-fetch-btn').addEventListener('click',()=>this._fetchPlaylist());
    document.getElementById('pl-url').addEventListener('keydown',e=>{if(e.key==='Enter')this._fetchPlaylist();});
    document.getElementById('pl-select-all').addEventListener('change',e=>this._toggleAllCards(e.target.checked));
    document.getElementById('pl-dl-btn').addEventListener('click',()=>this._downloadSelected());
  },

  async _fetchPlaylist(){
    const url=document.getElementById('pl-url').value.trim();
    if(!url){this.toast('Paste a playlist URL first','err');return;}
    const btn=document.getElementById('pl-fetch-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    // Show loader, hide other states
    document.getElementById('pl-empty').classList.add('hidden');
    document.getElementById('pl-results').classList.add('hidden');
    document.getElementById('pl-action-bar').style.display='none';
    document.getElementById('pl-loader').classList.remove('hidden');

    const settings=this._getSettings();
    const body={url};
    if(settings.cookie_file)body.cookie_file=settings.cookie_file;

    try{
      const r=await fetch('/api/playlist-info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const d=await r.json();
      if(r.ok&&d.entries?.length){
        this.plEntries=d.entries;
        this._renderPlaylistGrid(d);
        this.toast(`Found ${d.count} videos`,'ok');
      }else if(r.ok){
        this.toast('No videos found in playlist','err');
        document.getElementById('pl-empty').classList.remove('hidden');
      }else{
        this.toast(d.error||'Fetch failed','err');
        document.getElementById('pl-empty').classList.remove('hidden');
      }
    }catch{this.toast('Network error','err');document.getElementById('pl-empty').classList.remove('hidden');}
    finally{document.getElementById('pl-loader').classList.add('hidden');label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  _renderPlaylistGrid(data){
    const grid=document.getElementById('pl-grid');
    grid.innerHTML='';
    data.entries.forEach((entry,i)=>{
      const card=document.createElement('div');
      card.className='pl-card selected';
      card.dataset.index=i;
      card.dataset.url=entry.url||'';
      const dur=fmtDur(entry.duration);
      const thumb=entry.thumbnail||'';
      card.innerHTML=`<div class="card-check"></div>${thumb?`<img class="pl-thumb" src="${esc(thumb)}" alt="" loading="lazy" onerror="this.style.display='none'">`:'<div class="pl-thumb"></div>'}${dur?`<span class="pl-card-dur">${dur}</span>`:''}<div class="pl-card-body"><div class="pl-card-title">${esc(entry.title||'Untitled')}</div></div>`;
      card.addEventListener('click',()=>{card.classList.toggle('selected');this._updateSelCount();});
      grid.appendChild(card);
    });
    document.getElementById('pl-title').textContent=data.playlist_title||'Playlist';
    document.getElementById('pl-count-badge').textContent=`${data.count} videos`;
    document.getElementById('pl-select-all').checked=true;
    document.getElementById('pl-results').classList.remove('hidden');
    document.getElementById('pl-action-bar').style.display='flex';
    this._updateSelCount();
  },

  _toggleAllCards(checked){
    document.querySelectorAll('.pl-card').forEach(c=>{
      if(checked)c.classList.add('selected');else c.classList.remove('selected');
    });
    this._updateSelCount();
  },

  _updateSelCount(){
    const n=document.querySelectorAll('.pl-card.selected').length;
    document.getElementById('pl-sel-count').textContent=n;
    document.getElementById('pl-dl-btn').disabled=n===0;
    // Sync the select-all checkbox
    const total=document.querySelectorAll('.pl-card').length;
    document.getElementById('pl-select-all').checked=n===total&&total>0;
  },

  async _downloadSelected(){
    const cards=[...document.querySelectorAll('.pl-card.selected')];
    if(!cards.length){this.toast('No videos selected','err');return;}
    const btn=document.getElementById('pl-dl-btn');
    const label=btn.querySelector('.action-label'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    const settings=this._getSettings();
    const isVideo=this.plMode==='video';

    let queued=0;
    for(const card of cards){
      const url=card.dataset.url;
      if(!url)continue;
      const body={url,format_type:this.plMode,...settings};
      if(isVideo){
        body.quality=document.getElementById('pl-resolution').value;
        body.video_format=document.getElementById('pl-vformat').value;
      }else{
        body.audio_format=document.getElementById('pl-aformat').value;
      }
      try{
        const r=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if(r.ok)queued++;
      }catch{}
    }
    this.toast(`Queued ${queued} download${queued!==1?'s':''}`,'ok');
    this.log(`[Playlist] Queued ${queued} of ${cards.length} selected`);
    label.hidden=false;spin.hidden=true;btn.disabled=false;
  },

  /* ═══════════════ WEBSOCKET ═══════════════ */
  _connectWS(){
    this.ws=new WS(
      d=>this._onMsg(d),
      ()=>this._conn('live','Live'),
      ()=>this._conn('off','Offline'),
    );
    this.ws.connect();
  },
  _onMsg(d){
    if(d.type==='init')(d.tasks||[]).forEach(t=>this._upsert(t));
    else if(d.type==='progress')this._upsert(d);
    else if(d.type==='log')this._appendLog(d);
    this._counts();
  },
  _upsert(td){
    let c=this.cards.get(td.task_id);
    if(c)c.update(td);else{c=new DLCard(td);this.cards.set(td.task_id,c);document.getElementById('download-list').prepend(c.el);}
    this._empty();
  },
  _counts(){
    const n=[...this.cards.values()].filter(c=>!c.done).length;
    const b=document.getElementById('dl-count');b.textContent=n;b.hidden=n===0;
  },
  _empty(){document.getElementById('empty-state').classList.toggle('hidden',this.cards.size>0);},
  _conn(c,t){const el=document.getElementById('conn-status');el.className=`conn-indicator ${c}`;el.querySelector('.conn-label').textContent=t;},

  /* ── Log ──────────────────────────────────────────────── */
  _bindLog(){document.getElementById('log-clear')?.addEventListener('click',()=>{document.getElementById('log-output').innerHTML='<span class="log-muted">Log cleared.</span>';});},
  log(msg){
    const out=document.getElementById('log-output');if(!out)return;
    if(out.querySelector('.log-muted'))out.innerHTML='';
    const ts=new Date().toLocaleTimeString('en-GB',{hour12:false});
    out.textContent+=`[${ts}] ${msg}\n`;
    if(out.scrollHeight-out.scrollTop-out.clientHeight<80)out.scrollTop=out.scrollHeight;
  },
  _appendLog(data){
    const out=document.getElementById('log-output');if(!out)return;
    if(out.querySelector('.log-muted'))out.innerHTML='';
    out.textContent+=`[${data.task_id}] ${data.message}\n`;
    out.scrollTop=out.scrollHeight;
  },

  /* ── Settings ────────────────────────────────────────── */
  _bindSettings(){
    document.getElementById('set-dir-browse')?.addEventListener('click',async()=>{
      if(window.showDirectoryPicker){try{const h=await window.showDirectoryPicker({mode:'readwrite'});document.getElementById('set-dir').value=h.name;this._savePersistedSettings();}catch{}}
      else this.toast('Type the path manually','inf');
    });
    document.getElementById('set-cookie-browse')?.addEventListener('click',()=>{
      const inp=document.createElement('input');inp.type='file';inp.accept='.txt';
      inp.onchange=()=>{if(inp.files[0]){document.getElementById('set-cookie').value=inp.files[0].name;this._savePersistedSettings();}};
      inp.click();
    });
    document.getElementById('update-ytdlp-btn')?.addEventListener('click',()=>this._updateYtdlp());
    
    // Save on manual changes
    document.getElementById('set-dir')?.addEventListener('input',()=>this._savePersistedSettings());
    document.getElementById('set-cookie')?.addEventListener('input',()=>this._savePersistedSettings());
  },

  _savePersistedSettings(){
    const settings = this._getSettings();
    localStorage.setItem('hvd_settings', JSON.stringify({
      output_dir: settings.output_dir || '',
      cookie_file: settings.cookie_file || ''
    }));
  },

  _loadPersistedSettings(){
    try {
      const saved = localStorage.getItem('hvd_settings');
      if (saved) {
        const settings = JSON.parse(saved);
        const dirEl = document.getElementById('set-dir');
        const cookieEl = document.getElementById('set-cookie');
        if (dirEl && settings.output_dir) dirEl.value = settings.output_dir;
        if (cookieEl && settings.cookie_file) cookieEl.value = settings.cookie_file;
      }
    } catch(e) {}
  },

  async _updateYtdlp(){
    const btn=document.getElementById('update-ytdlp-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    const out=document.getElementById('update-output');
    label.hidden=true;spin.hidden=false;btn.disabled=true;
    out.style.display='none';

    try{
      const r=await fetch('/api/update-ytdlp',{method:'POST'});
      const d=await r.json();
      out.textContent=d.output||'No output';
      out.style.display='block';
      this.toast(d.success?'yt-dlp updated':'Update failed',d.success?'ok':'err');
    }catch{this.toast('Network error','err');}
    finally{label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  /* ── Theme ───────────────────────────────────────────── */
  _bindTheme(){
    const saved=localStorage.getItem('hvd-theme')||'violet-cyan';
    this._applyTheme(saved);
    document.querySelectorAll('.theme-swatches .swatch').forEach(s=>{
      s.addEventListener('click',()=>{
        const name=s.dataset.theme;
        this._applyTheme(name);
        localStorage.setItem('hvd-theme',name);
        this.toast(`Accent theme changed`,'ok');
      });
    });
  },
  _applyTheme(name){
    const t=this.themes[name]||this.themes['violet-cyan'];
    Object.entries(t).forEach(([k,v])=>document.documentElement.style.setProperty(k,v));
    document.querySelectorAll('.theme-swatches .swatch').forEach(s=>{
      s.classList.toggle('active',s.dataset.theme===name);
    });
  },

  /* ── Clipboard ───────────────────────────────────────── */
  _bindClipboard(){
    window.addEventListener('focus',async()=>{
      const inp=document.getElementById('single-url');
      if(inp&&!inp.value.trim()){
        try{
          const text=await navigator.clipboard.readText();
          const url=text.trim();
          if(url.startsWith('http://')||url.startsWith('https://')){
            if(/youtube\.com|youtu\.be|vimeo\.com|soundcloud\.com|instagram\.com|facebook\.com|tiktok\.com/.test(url)){
              inp.value=url;
              this.toast('Auto-pasted link from clipboard','inf');
            }
          }
        }catch(e){}
      }
    });
  },

  /* ── Notification ────────────────────────────────────── */
  notify(title){
    if(this.notified.has(title))return;
    this.notified.add(title);
    if(window.Notification&&Notification.permission==='granted'){
      try{new Notification('Horizon Video Downloader',{body:`Download Completed:\n${title}`});}catch(e){}
    }
  },

  /* ── Toast ───────────────────────────────────────────── */
  toast(msg,type='inf'){
    const c=document.getElementById('toast-container');
    const icons={ok:IC.tOk,err:IC.tErr,inf:IC.tInfo};
    const t=document.createElement('div');t.className=`toast ${type}`;
    t.innerHTML=`${icons[type]||icons.inf}<span>${msg}</span>`;
    c.appendChild(t);
    setTimeout(()=>{t.classList.add('bye');t.onanimationend=()=>t.remove();},3500);
  },

  /* ═══════════════ SOCIAL GALLERY TAB ═══════════════ */
  _bindSocial(){
    document.getElementById('social-fetch-btn')?.addEventListener('click',()=>this._fetchSocial());
    document.getElementById('social-url')?.addEventListener('keydown',e=>{if(e.key==='Enter')this._fetchSocial();});
    document.getElementById('social-dl-btn')?.addEventListener('click',()=>this._downloadSocialSelected());
    
    // Wire up thumbnail filtering toggle
    document.getElementById('social-filter-thumbs')?.addEventListener('change',e=>{
      const hide=e.target.checked;
      document.querySelectorAll('.social-card').forEach(c=>{
        if(c.dataset.type==='image')c.classList.toggle('hidden',hide);
      });
    });
    
    // Wire up paste button for social tab
    const pbtn = document.querySelector('.paste-btn[data-target="social-url"]');
    if (pbtn) {
      pbtn.addEventListener('click', async () => {
        const target = document.getElementById(pbtn.dataset.target);
        if (!target) return;
        try {
          const t = await navigator.clipboard.readText();
          if (t) {
            target.value = t.trim();
            target.dispatchEvent(new Event('input'));
          }
        } catch {
          this.toast('Clipboard access denied', 'err');
        }
      });
    }
  },

  async _fetchSocial(){
    const url=document.getElementById('social-url').value.trim();
    if(!url){this.toast('Paste a Facebook or Instagram post URL first','err');return;}
    const btn=document.getElementById('social-fetch-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    const grid=document.getElementById('social-grid');
    grid.innerHTML='';
    document.getElementById('social-preview-section').style.display='none';

    const settings=this._getSettings();
    const query = new URLSearchParams({ url });
    if(settings.cookie_file)query.append('cookie_file',settings.cookie_file);

    try{
      const r=await fetch(`/api/fetch-social?${query.toString()}`);
      const d=await r.json();
      if(r.ok && d.length){
        this._renderSocialGrid(d);
        this.toast(`Found ${d.length} media items`,'ok');
      }else{
        this.toast(d.error||'No media items found','err');
      }
    }catch{this.toast('Network error','err');}
    finally{label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  _renderSocialGrid(items){
    const grid=document.getElementById('social-grid');
    grid.innerHTML='';
    const hideThumbs = document.getElementById('social-filter-thumbs')?.checked || false;
    items.forEach((item,i)=>{
      const card=document.createElement('div');
      card.className='social-card selected';
      if(hideThumbs && item.type === 'image') card.classList.add('hidden');
      card.dataset.url=item.url;
      card.dataset.type=item.type;
      card.style.backgroundImage=`url('${item.thumbnail || item.url}')`;
      
      const badgeText = item.type === 'video' ? 'Video' : 'Image';
      card.innerHTML=`<div class="checkbox-overlay"></div><span class="type-badge">${badgeText}</span>`;
      card.addEventListener('click',()=>{
        card.classList.toggle('selected');
      });
      grid.appendChild(card);
    });
    document.getElementById('social-preview-section').style.display='block';
  },

  async _downloadSocialSelected(){
    const cards=[...document.querySelectorAll('.social-card.selected')];
    if(!cards.length){this.toast('No items selected','err');return;}
    const btn=document.getElementById('social-dl-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    const urls=cards.map(c=>c.dataset.url);
    const settings=this._getSettings();
    const body={
      urls,
      output_dir:settings.output_dir,
      image_format:document.getElementById('social-img-format')?.value || 'original',
      video_format:document.getElementById('social-vid-format')?.value || 'mp4'
    };

    try{
      const r=await fetch('/api/download-social',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)
      });
      const d=await r.json();
      if(r.ok&&d.success){
        this.toast(d.message||'Download complete','ok');
        cards.forEach(c=>c.classList.remove('selected'));
      }else{
        this.toast(d.error||'Download failed','err');
      }
    }catch{this.toast('Network error','err');}
    finally{label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  async _loadHistory(){
    const rows=document.getElementById('history-rows');
    if(!rows)return;
    try{
      const r=await fetch('/api/history');
      const data=r.ok?await r.json():[];
      if(data.length===0){
        rows.innerHTML='<tr><td colspan="4" style="padding:20px; text-align:center; color:var(--text-3);">No download history found.</td></tr>';
        return;
      }
      rows.innerHTML=data.map(item=>{
        const dateStr=item.timestamp||'N/A';
        const title=item.title||'Untitled';
        const url=item.url||'';
        const status=item.status||'queued';
        return `<tr style="border-bottom:1px solid rgba(255,255,255,0.05);"><td style="padding:12px 8px; font-size:0.85rem; color:var(--text-3);">${esc(dateStr)}</td><td style="padding:12px 8px; font-weight:500;" title="${esc(title)}">${esc(title)}</td><td style="padding:12px 8px; font-size:0.85rem;" title="${esc(url)}"><a href="${esc(url)}" target="_blank" style="color:var(--accent); text-decoration:none;">${esc(url)}</a></td><td style="padding:12px 8px;"><span class="badge ${esc(status)}">${esc(status)}</span></td></tr>`;
      }).join('');
    }catch(e){
      rows.innerHTML='<tr><td colspan="4" style="padding:20px; text-align:center; color:var(--accent-dim);">Failed to load history.</td></tr>';
    }
  },
};

document.addEventListener('DOMContentLoaded',()=>App.init());
