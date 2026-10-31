'use strict';
let state = { accounts: [], profiles: [], audit: [] };
let currentView = 'overview';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const gb = n => (n / 1e9).toLocaleString(undefined, {maximumFractionDigits: 3}) + ' GB';
const date = n => n == null ? 'Starts on activation' : new Date(n * 1000).toLocaleString('en-ZA', {timeZone: 'Africa/Johannesburg'}) + ' SAST';
function notice(message, retry = false) {
  $('notice').textContent = message; $('notice').hidden = false;
  $('retry-connect').hidden = !retry;
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function friendlyError(error) {
  if (error.name === 'AbortError') return 'The VPN admin server timed out. Check the hosting service and database, then retry.';
  if (error instanceof TypeError) return 'Cannot reach the VPN admin server. Check your internet connection and hosting status, then retry.';
  return error.message || 'Unexpected admin server error';
}
// Only safe GET requests are retried. Never replay a profile or account creation.
async function requestJson(path, options = {}) {
  const attempts = !options.method || options.method === 'GET' ? 3 : 1;
  for (let i = 0; i < attempts; i++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {...options, credentials:'same-origin', cache:'no-store', signal:controller.signal});
      if (!(response.headers.get('Content-Type') || '').toLowerCase().includes('application/json')) {
        if (response.status >= 500 && i < attempts-1) {await delay(1000 * (i+1)); continue;}
        throw Error('Admin server returned HTTP ' + response.status + ' instead of JSON. Check server logs.');
      }
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401 && path.startsWith('/admin/api/')) {
          $('workspace').hidden = true; $('login-panel').hidden = false;
        }
        if ([502,503,504].includes(response.status) && i < attempts-1) {
          await delay(1000 * (i+1)); continue;
        }
        throw Error(data.error || 'Request failed (HTTP ' + response.status + ')');
      }
      return data;
    } catch(error) {
      if (i === attempts-1 || !(error instanceof TypeError || error.name === 'AbortError')) throw Error(friendlyError(error));
      await delay(1000 * (i+1));
    } finally { clearTimeout(timer); }
  }
}
async function api(path, method = 'GET', body) {
  return requestJson('/admin/api/' + path, {method,
    headers:{'Content-Type':'application/json','X-TPP-Request':'1'},
    body: body === undefined ? undefined : JSON.stringify(body)});
}
let refreshInFlight = null;
async function refresh() {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const result = await api('state');
    if (!Array.isArray(result.accounts) || !Array.isArray(result.profiles) || !Array.isArray(result.audit))
      throw Error('Server returned incomplete profile data.');
    state = result; $('login-panel').hidden = true; $('workspace').hidden = false;
    $('retry-connect').hidden = true; render();
  })().finally(() => {refreshInFlight = null;});
  return refreshInFlight;
}
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
  $('gateway-status').textContent = state.profiles.some(p=>p.enabled) ? 'Imported profiles ready. Customers connect with an assigned access code. Usage is app reported; connectivity depends on the supplier server.' : 'Import a connection JSON profile and enable it to get started.';
  const checked = [...document.querySelectorAll('[name="profile_ids"]:checked')].map(e => e.value);
  $('profile-choices').innerHTML = state.profiles.filter(p=>p.engine==='xray'&&p.enabled).map(p=>`<label class="check"><input type="checkbox" name="profile_ids" value="${escape(p.id)}" ${checked.includes(p.id)?'checked':''}>${escape(p.name)} · ${escape(p.carrier)}</label>`).join('') || '<p class="muted">Create an enabled connection profile first.</p>';
  renderAccounts();
  $('profile-list').innerHTML = state.profiles.filter(p=>p.engine==='xray').map(p=>`<div class="profile-row"><div class="row-top"><strong>${escape(p.name)}</strong><span class="tag">${escape(p.carrier)} · v${p.version}</span></div><p>${p.enabled?'Enabled':'Disabled'} · Imported connection</p><p>${p.insecure_tls?'Unverified TLS — test only':'TLS certificate checks enabled'} · App-reported usage</p><div class="row-actions"><button data-edit-profile="${escape(p.id)}">Replace import</button><button data-toggle-xray="${escape(p.id)}">${p.enabled?'Disable':'Enable'}</button></div></div>`).join('') || '<p>No imported profiles yet.</p>';
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
$('edit-form').addEventListener('submit',e=>{e.preventDefault();const f=e.target;busy(f,async()=>{const d=new FormData(f),body={label:d.get('label'),quota_bytes:Math.round(Number(d.get('quota'))*1e9),duration_seconds:Math.round(Number(d.get('duration_hours'))*3600),suspended:d.has('suspended'),reset_device:d.has('reset_device')};if(Number(d.get('days'))>0)body.extend_seconds=Number(d.get('days'))*86400;await api('accounts/'+d.get('id'),'PATCH',body);$('edit-dialog').close();await refresh();notice('Account updated.');});});
$('copy-code').onclick=()=>navigator.clipboard.writeText($('code-value').textContent).then(()=>notice('Code copied.')).catch(()=>notice('Select and copy the code manually.'));
$('search').oninput=renderAccounts;
$('edit-cancel').onclick=()=>$('edit-dialog').close();
$('logout').onclick=async()=>{try{await api('logout','POST',{});state={accounts:[],profiles:[],audit:[]};$('code-value').textContent='';$('new-code').hidden=true;$('workspace').hidden=true;$('login-panel').hidden=false;}catch(e){notice(e.message);}};
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{
 if(b.dataset.view)view(b.dataset.view);
 if(b.dataset.days){$('code-form').elements.duration.value=b.dataset.days;$('code-form').elements.unit.value='86400';$('code-form').elements.kind.value='paid';}
 if(b.dataset.hours){$('code-form').elements.duration.value=b.dataset.hours;$('code-form').elements.unit.value='3600';$('code-form').elements.kind.value='trial';}
 if(b.dataset.editProfile){const p=state.profiles.find(p=>p.id===b.dataset.editProfile),f=$('xray-form');f.reset();f.elements.id.value=p.id;f.elements.name.value=p.name;f.elements.carrier.value=p.carrier;f.elements.enabled.checked=!!p.enabled;f.elements.allow_insecure.checked=!!p.insecure_tls;$('xray-title').textContent='Replace imported profile';notice('Paste the complete JSON again to replace this imported profile. Stored passwords are not returned to the browser.');f.scrollIntoView({behavior:'smooth'});}
 if(b.dataset.toggleXray){const p=state.profiles.find(p=>p.id===b.dataset.toggleXray);await api('xray-profiles/'+p.id,'PATCH',{enabled:!p.enabled});await refresh();}
 if(b.dataset.editAccount){const a=state.accounts.find(a=>a.id===b.dataset.editAccount),f=$('edit-form');f.reset();f.elements.id.value=a.id;f.elements.label.value=a.label;f.elements.quota.value=a.quota/1e9;f.elements.duration_hours.value=a.duration/3600;f.elements.suspended.checked=!!a.suspended;$('edit-dialog').showModal();}
 if(b.dataset.suspend){const a=state.accounts.find(a=>a.id===b.dataset.suspend);await api('accounts/'+a.id,'PATCH',{suspended:!a.suspended});await refresh();}
 if(b.dataset.delete&&confirm('Delete this account and revoke its access? This cannot be undone.')){await api('accounts/'+b.dataset.delete,'DELETE');await refresh();}
}catch(error){notice(error.message);}});
async function initialize() {
  try {
    const setup=await requestJson('/setup-status');
    if(setup.setup_required){
      $('login-panel').hidden=false;
      notice('First-time setup: open this service in Render → Environment. Add TPP_BOOTSTRAP_PASSWORD with a unique password of at least 14 characters, then save and redeploy. Sign in here as admin with that password.');
      return;
    }
    await refresh();
  } catch(e){if(e.message!=='Sign in to continue')notice(friendlyError(e), true);}
}
$('retry-connect').onclick = () => {notice('Reconnecting…');initialize();};
view(currentView);initialize();
setInterval(()=>{if(!$('workspace').hidden && !refreshInFlight)refresh().catch(e=>notice(friendlyError(e),true));},30000);


function checkImport(value) {
  let config;
  try { config = JSON.parse(value); }
  catch (_) {throw Error('Invalid JSON: paste the complete unlocked Xray configuration.');}
  if (!config || !Array.isArray(config.outbounds)) throw Error('Missing outbounds array.');
  const tunnels = config.outbounds.filter(o => o && ['vless','trojan'].includes(o.protocol));
  if (tunnels.length !== 1) throw Error('Use exactly one VLESS or Trojan outbound per profile.');
  const outbound = tunnels[0];
  if (outbound.protocol === 'vless') {
    const server = outbound.settings?.vnext?.[0];
    if (!server?.address || !Number.isInteger(server.port) || !server.users?.[0]?.id)
      throw Error('VLESS requires a server hostname, port and UUID. Replace example placeholders.');
  }
  if (!['tcp','raw',undefined].includes(outbound.streamSettings?.network) || outbound.streamSettings?.security !== 'tls')
    throw Error('Currently supported transport: TCP with TLS.');
  return outbound.protocol.toUpperCase();
}
$('vless-template').onclick = () => {
  const form=$('xray-form');
  if (form.elements.config.value.trim() && !confirm('Replace your current JSON with a VLESS example?')) return;
  form.elements.config.value = "{\n  \"dns\": {\n    \"servers\": [\n      \"1.1.1.1\"\n    ]\n  },\n  \"outbounds\": [\n    {\n      \"protocol\": \"vless\",\n      \"settings\": {\n        \"vnext\": [\n          {\n            \"address\": \"REPLACE_WITH_SERVER_HOST\",\n            \"port\": 443,\n            \"users\": [\n              {\n                \"id\": \"REPLACE_WITH_VLESS_UUID\",\n                \"encryption\": \"none\"\n              }\n            ]\n          }\n        ]\n      },\n      \"streamSettings\": {\n        \"network\": \"tcp\",\n        \"security\": \"tls\",\n        \"tlsSettings\": {\n          \"serverName\": \"REPLACE_WITH_CERTIFICATE_HOST\",\n          \"allowInsecure\": false\n        }\n      }\n    }\n  ]\n}";
  form.elements.allow_insecure.checked=false;
  $('import-feedback').textContent='Replace all example hostnames and the UUID with your actual supplier details. Keep TLS verification enabled.';
  form.elements.config.focus();
};
$('validate-import').onclick = () => {
  try {$('import-feedback').textContent=checkImport($('xray-form').elements.config.value)+' structure looks correct; the server validates it on save.';}
  catch(error) {$('import-feedback').textContent=error.message;}
};
$('xray-form').addEventListener('submit',e=>{e.preventDefault();const f=e.target;busy(f,async()=>{
  const d=new FormData(f),id=d.get('id'),protocol=checkImport(d.get('config'));
  await api('xray-profiles'+(id?'/'+id:''),id?'PUT':'POST',
    {name:d.get('name'),carrier:d.get('carrier'),config:d.get('config'),allow_insecure:d.has('allow_insecure'),enabled:d.has('enabled')});
  f.reset();f.elements.id.value='';$('xray-title').textContent='Import connection JSON';
  $('import-feedback').textContent='';await refresh();
  notice(protocol+' profile saved. Assign to an access account; live connectivity still needs testing.');
});});
$('xray-reset').onclick=()=>{$('xray-form').reset();$('xray-form').elements.id.value='';$('xray-title').textContent='Import connection JSON';$('import-feedback').textContent='';};

