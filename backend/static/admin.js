'use strict';
let state = { accounts: [], profiles: [], audit: [] };
let currentView = 'overview';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const gb = n => (n / 1e9).toLocaleString(undefined, {maximumFractionDigits: 3}) + ' GB';
const date = n => n == null ? 'Starts on activation' : new Date(n * 1000).toLocaleString('en-ZA', {timeZone: 'Africa/Johannesburg'}) + ' SAST';
function notice(message) { $('notice').textContent = message; $('notice').hidden = false; }
async function api(path, method = 'GET', body) {
  const response = await fetch('/admin/api/' + path, {method, credentials: 'same-origin', headers: {'Content-Type':'application/json','X-TPP-Request':'1'}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) { if (response.status === 401) { $('workspace').hidden = true; $('login-panel').hidden = false; } throw Error(data.error || 'Request failed'); }
  return data;
}
async function refresh() { state = await api('state'); $('login-panel').hidden = true; $('workspace').hidden = false; render(); }
function view(name) {
  currentView = name;
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== name + '-view');
  document.querySelectorAll('nav button').forEach(el => el.classList.toggle('selected', el.dataset.view === name));
  $('page-title').textContent = {overview:'Overview',accounts:'Access accounts',profiles:'Connection profiles',activity:'Activity'}[name];
}
function render() {
  $('stat-total').textContent = state.accounts.length;
  $('stat-active').textContent = state.accounts.filter(a => a.status === 'active').length;
  $('stat-pending').textContent = state.accounts.filter(a => a.status === 'pending').length;
  $('stat-data').textContent = gb(state.accounts.reduce((sum, a) => sum + a.used, 0));
  $('gateway-status').textContent = state.gateway_enabled ? 'TLS listener configured. Confirm live routing and certificate health before selling access.' : 'Gateway not configured. Admin functions work, but VPN connections are unavailable until server setup is complete.';
  const checked = [...document.querySelectorAll('[name="profile_ids"]:checked')].map(e => e.value);
  $('profile-choices').innerHTML = state.profiles.filter(p=>p.enabled).map(p=>`<label class="check"><input type="checkbox" name="profile_ids" value="${escape(p.id)}" ${checked.includes(p.id)?'checked':''}>${escape(p.name)} · ${escape(p.carrier)}</label>`).join('') || '<p class="muted">Create an enabled connection profile first.</p>';
  renderAccounts();
  $('profile-list').innerHTML = state.profiles.map(p=>`<div class="profile-row"><div class="row-top"><strong>${escape(p.name)}</strong><span class="tag">${escape(p.carrier)} · v${p.version}</span></div><p>${escape(p.server)}:${p.port} · ${p.enabled?'Enabled':'Disabled'}</p><p>SNI ${escape(p.sni)} · TLS ${escape(p.tls_min)}+</p><div class="row-actions"><button data-edit-profile="${escape(p.id)}">Edit profile</button></div></div>`).join('') || '<p>No profiles yet.</p>';
  $('audit-list').innerHTML = state.audit.map(a=>`<div class="audit-row"><strong>${escape(a.action.replaceAll('_',' '))}</strong><p class="muted">${escape(date(a.at))} · ${escape(a.subject.slice(0,8))} ${escape(a.detail)}</p></div>`).join('') || '<p>No events yet.</p>';
}
function renderAccounts() {
  const query = $('search').value.toLowerCase();
  $('account-list').innerHTML = state.accounts.filter(a=>a.label.toLowerCase().includes(query)||a.id.toLowerCase().includes(query)).map(a=>`<div class="account-row"><div class="row-top"><strong>${escape(a.label)}</strong><span class="tag ${escape(a.status)}">${escape(a.status)}</span></div><p>${a.online?'● Online · ':''}${a.kind==='trial'?'Free trial':'Paid access'} · ${Math.round(a.duration/3600*10)/10} hours · ${gb(a.used)} used / ${gb(a.quota)}</p><p>Reference: ${escape(a.id)}</p><div class="meter"><div data-width="${Math.min(100,a.used/a.quota*100)}"></div></div><p>Expires: ${escape(date(a.expires))}</p><div class="row-actions"><button data-edit-account="${escape(a.id)}">Edit / renew</button><button data-suspend="${escape(a.id)}">${a.suspended?'Resume':'Suspend'}</button><button class="danger" data-delete="${escape(a.id)}">Delete</button></div></div>`).join('') || '<p class="muted">No matching accounts.</p>';
  document.querySelectorAll('[data-width]').forEach(el=>el.style.width=el.dataset.width+'%');
}
function busy(form, run) { const buttons = [...form.querySelectorAll('button')]; buttons.forEach(b=>b.disabled=true); return run().catch(e=>notice(e.message)).finally(()=>buttons.forEach(b=>b.disabled=false)); }
$('login-form').addEventListener('submit', e=>{e.preventDefault();const f=e.target;busy(f,async()=>{await api('login','POST',Object.fromEntries(new FormData(f)));f.reset();$('notice').hidden=true;await refresh();});});
$('code-form').addEventListener('submit',e=>{e.preventDefault();const f=e.target;busy(f,async()=>{const d=new FormData(f);const result=await api('accounts','POST',{label:d.get('label'),kind:d.get('kind'),duration_seconds:Number(d.get('duration'))*Number(d.get('unit')),quota_bytes:Math.round(Number(d.get('quota'))*Number(d.get('quota_unit'))),profile_ids:d.getAll('profile_ids')});$('new-code').hidden=false;$('code-value').textContent=result.code;notice('Access code created. Its timer has not started.');await refresh();});});
$('profile-form').addEventListener('submit',e=>{e.preventDefault();const f=e.target;busy(f,async()=>{const d=new FormData(f),id=d.get('id');await api('profiles'+(id?'/'+id:''),id?'PUT':'POST',{name:d.get('name'),carrier:d.get('carrier'),server:d.get('server'),port:Number(d.get('port')),sni:d.get('sni'),tls_min:d.get('tls_min'),enabled:d.has('enabled')});f.reset();f.elements.id.value='';$('profile-title').textContent='New connection profile';await refresh();notice('Profile saved. Active sessions using the previous version will disconnect.');});});
$('edit-form').addEventListener('submit',e=>{e.preventDefault();const f=e.target;busy(f,async()=>{const d=new FormData(f),body={label:d.get('label'),quota_bytes:Math.round(Number(d.get('quota'))*1e9),duration_seconds:Math.round(Number(d.get('duration_hours'))*3600),suspended:d.has('suspended'),reset_device:d.has('reset_device')};if(Number(d.get('days'))>0)body.extend_seconds=Number(d.get('days'))*86400;await api('accounts/'+d.get('id'),'PATCH',body);$('edit-dialog').close();await refresh();notice('Account updated.');});});
$('copy-code').onclick=()=>navigator.clipboard.writeText($('code-value').textContent).then(()=>notice('Code copied.')).catch(()=>notice('Select and copy the code manually.'));
$('search').oninput=renderAccounts;
$('profile-reset').onclick=()=>{$('profile-form').reset();$('profile-form').elements.id.value='';$('profile-title').textContent='New connection profile';};
$('edit-cancel').onclick=()=>$('edit-dialog').close();
$('logout').onclick=async()=>{try{await api('logout','POST',{});state={accounts:[],profiles:[],audit:[]};$('code-value').textContent='';$('new-code').hidden=true;$('workspace').hidden=true;$('login-panel').hidden=false;}catch(e){notice(e.message);}};
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{
 if(b.dataset.view)view(b.dataset.view);
 if(b.dataset.days){$('code-form').elements.duration.value=b.dataset.days;$('code-form').elements.unit.value='86400';$('code-form').elements.kind.value='paid';}
 if(b.dataset.hours){$('code-form').elements.duration.value=b.dataset.hours;$('code-form').elements.unit.value='3600';$('code-form').elements.kind.value='trial';}
 if(b.dataset.editProfile){const p=state.profiles.find(p=>p.id===b.dataset.editProfile),f=$('profile-form');for(const k of ['id','name','carrier','server','port','sni','tls_min'])f.elements[k].value=p[k];f.elements.enabled.checked=!!p.enabled;$('profile-title').textContent='Edit connection profile';f.scrollIntoView({behavior:'smooth'});}
 if(b.dataset.editAccount){const a=state.accounts.find(a=>a.id===b.dataset.editAccount),f=$('edit-form');f.reset();f.elements.id.value=a.id;f.elements.label.value=a.label;f.elements.quota.value=a.quota/1e9;f.elements.duration_hours.value=a.duration/3600;f.elements.suspended.checked=!!a.suspended;$('edit-dialog').showModal();}
 if(b.dataset.suspend){const a=state.accounts.find(a=>a.id===b.dataset.suspend);await api('accounts/'+a.id,'PATCH',{suspended:!a.suspended});await refresh();}
 if(b.dataset.delete&&confirm('Delete this account and revoke its access? This cannot be undone.')){await api('accounts/'+b.dataset.delete,'DELETE');await refresh();}
}catch(error){notice(error.message);}});
async function initialize() {
  try {
    const response=await fetch('/setup-status',{credentials:'same-origin'});
    const setup=await response.json();
    if(setup.setup_required){
      $('login-panel').hidden=false;
      notice('First-time setup: open this service in Render → Environment. Add TPP_BOOTSTRAP_PASSWORD with a unique password of at least 14 characters, then save and redeploy. Sign in here as admin with that password.');
      return;
    }
    await refresh();
  } catch(e){if(e.message!=='Sign in to continue')notice(e.message);}
}
view(currentView);initialize();
setInterval(()=>{if(!$('workspace').hidden)refresh().catch(e=>notice(e.message));},30000);
