'use strict';
let state = { accounts: [], profiles: [], audit: [] };
let currentView = 'profiles';
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
    if (!$('retry-connect').hidden) $('notice').hidden = true;
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
  renderAccounts();
  $('profile-list').innerHTML = state.profiles.filter(p=>p.engine==='xray').map(p=>`<div class="profile-row"><div class="row-top"><strong>${escape(p.name)}</strong><span class="tag">${escape(p.carrier)} · v${p.version}</span></div><p>${p.enabled?'Enabled':'Disabled'} · Imported connection</p><p>${p.insecure_tls?'Unverified TLS — test only':'TLS certificate checks enabled'} · App-reported usage</p><div class="row-actions"><button data-edit-profile="${escape(p.id)}">Replace import</button><button data-toggle-xray="${escape(p.id)}">${p.enabled?'Disable':'Enable'}</button></div></div>`).join('') || '<p>No imported profiles yet.</p>';
  $('audit-list').innerHTML = state.audit.map(a=>`<div class="audit-row"><strong>${escape(a.action.replaceAll('_',' '))}</strong><p class="muted">${escape(date(a.at))} · ${escape(a.subject.slice(0,8))} ${escape(a.detail)}</p></div>`).join('') || '<p>No events yet.</p>';
}
function renderAccounts() {
  const query = $('search').value.toLowerCase();
  const filter = $('account-status').value;
  $('account-list').innerHTML = state.accounts.filter(a => (filter === 'all' || (a.status === 'active') === (filter === 'active')) &&
    (a.label.toLowerCase().includes(query) || a.id.toLowerCase().includes(query))).map(a=>`<div class="account-row"><div class="row-top"><strong>${escape(a.label)}</strong><span class="tag ${escape(a.status)}">${a.status === 'active' ? 'Active' : 'Inactive · ' + escape(a.status)}</span></div><p>${a.online && a.status === 'active'?'● Online · ':''}${a.kind==='trial'?'Free trial · '+a.device_count+'/50 devices · shared data':'Paid access · 1 device'} · ${Math.round(a.duration/3600*10)/10} hours · ${gb(a.used)} used / ${gb(a.quota)}</p><p>Code network: ${escape(a.carrier||'Needs admin assignment')}</p><p>Reference: ${escape(a.id)}</p><div class="meter"><div data-width="${Math.min(100,a.used/a.quota*100)}"></div></div><p>Expires: ${escape(date(a.expires))}</p><div class="row-actions"><button data-edit-account="${escape(a.id)}">Edit / Renew</button>${a.suspended
    ? `<button data-account="${escape(a.id)}" data-access-state="enabled">Resume</button>`
    : `<button data-account="${escape(a.id)}" data-access-state="paused">Pause</button><button data-account="${escape(a.id)}" data-access-state="suspended">Suspend</button>`}<button class="danger" data-delete="${escape(a.id)}">Delete</button></div></div>`).join('') || '<p class="muted">No matching accounts.</p>';
  document.querySelectorAll('[data-width]').forEach(el=>el.style.width=el.dataset.width+'%');
}
function busy(form, run) { const buttons = [...form.querySelectorAll('button')]; buttons.forEach(b=>b.disabled=true); return run().catch(e=>notice(e.message)).finally(()=>buttons.forEach(b=>b.disabled=false)); }
$('login-form').addEventListener('submit', e=>{e.preventDefault();const f=e.target;busy(f,async()=>{await api('login','POST',Object.fromEntries(new FormData(f)));f.reset();$('notice').hidden=true;await refresh();});});
const editForm = $('edit-form');
function showAssignedProfiles(carrier, assigned = []) {
  $('edit-profile-choices').innerHTML = state.profiles.filter(p =>
    assigned.includes(p.id) || (p.enabled && (p.carrier === carrier || p.carrier === 'Any'))
  ).map(p => `<label class="check"><input type="checkbox" name="edit_profile_ids"
    value="${escape(p.id)}" ${assigned.includes(p.id) ? 'checked' : ''}>${escape(p.name)} · ${escape(p.carrier)}</label>`).join('')
    || '<p class="muted">No profiles for this network.</p>';
}
editForm.elements.carrier.onchange = () => showAssignedProfiles(editForm.elements.carrier.value);
$('edit-cancel').onclick = () => $('edit-dialog').close();
editForm.addEventListener('submit', e => {
  e.preventDefault();
  busy(editForm, async () => {
    const data = new FormData(editForm);
    const account = state.accounts.find(a => a.id === data.get('id'));
    if (!account) throw Error('This account is no longer available.');
    const changes = {};
    const label = data.get('label').trim();
    const quota = Math.round(Number(data.get('quota')) * 1e9);
    const duration = Math.round(Number(data.get('duration_hours')) * 3600);
    const carrier = data.get('carrier');
    const profiles = data.getAll('edit_profile_ids');
    if (label !== account.label) changes.label = label;
    if (quota !== account.quota) changes.quota_bytes = quota;
    if (duration !== account.duration) changes.duration_seconds = duration;
    if (carrier !== (account.carrier || '') || profiles.length !== account.profile_ids.length ||
        profiles.some(id => !account.profile_ids.includes(id))) {
      changes.carrier = carrier;
      changes.profile_ids = profiles;
    }
    if (Number(data.get('days')) > 0) changes.extend_seconds = Number(data.get('days')) * 86400;
    if (data.has('reset_device')) changes.reset_device = true;
    if (Object.keys(changes).length) {
      await api('accounts/' + account.id, 'PATCH', changes);
      await refresh();
      notice(changes.extend_seconds ? 'Account renewed.' : 'Account updated.');
    }
    $('edit-dialog').close();
  });
});
$('copy-code').onclick=()=>navigator.clipboard.writeText($('code-value').textContent).then(()=>notice('Code copied.')).catch(()=>notice('Select and copy the code manually.'));
$('search').oninput=renderAccounts;
$('account-status').onchange=renderAccounts;
$('logout').onclick=async()=>{try{await api('logout','POST',{});state={accounts:[],profiles:[],audit:[]};resetImport();$('code-value').textContent='';$('new-code').hidden=true;$('workspace').hidden=true;$('login-panel').hidden=false;}catch(e){notice(e.message);}};
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{
 if(b.dataset.view)view(b.dataset.view);
 if(b.dataset.editProfile){const p=state.profiles.find(p=>p.id===b.dataset.editProfile),f=$('xray-form');f.reset();f.elements.id.value=p.id;f.elements.name.value=p.name;setImportMode(p);f.elements.carrier.value=p.carrier;f.elements.enabled.checked=!!p.enabled;f.elements.allow_insecure.checked=!!p.insecure_tls;notice('Paste the complete JSON again to replace this imported profile. Stored passwords are not returned to the browser.');f.scrollIntoView({behavior:'smooth'});}
 if(b.dataset.toggleXray){const p=state.profiles.find(p=>p.id===b.dataset.toggleXray);await api('xray-profiles/'+p.id,'PATCH',{enabled:!p.enabled});await refresh();}
 if(b.dataset.editAccount){
   const account = state.accounts.find(a => a.id === b.dataset.editAccount);
   editForm.reset();
   editForm.elements.id.value = account.id;
   editForm.elements.label.value = account.label;
   editForm.elements.carrier.value = account.carrier || '';
   editForm.elements.quota.value = account.quota / 1e9;
   editForm.elements.duration_hours.value = account.duration / 3600;
   showAssignedProfiles(account.carrier, account.profile_ids);
   $('edit-dialog').showModal();
 }
 if(b.dataset.accessState){
   b.disabled = true;
   try {
     await api('accounts/'+b.dataset.account,'PATCH',{access_state:b.dataset.accessState});
     await refresh();
   } finally { b.disabled = false; }
 }
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
    const uuid=server?.users?.[0]?.id;
    if (typeof server?.address !== 'string' || !server.address || server.address.startsWith('REPLACE_'))
      throw Error('VLESS server address is missing or still an example. Set settings.vnext[0].address to your server hostname or IP.');
    const port = typeof server.port === 'string' && /^[0-9]{1,5}$/.test(server.port.trim()) ? Number(server.port.trim()) : server.port;
    if (!Number.isInteger(port) || port < 1 || port > 65535)
      throw Error('VLESS server port must be a number from 1 to 65535, such as 443.');
    // Match the UUID forms accepted by Python uuid.UUID on the server.
    const uuidHex = typeof uuid === 'string' ? uuid.replaceAll('urn:', '').replaceAll('uuid:', '').replace(/^[{}]+|[{}]+$/g, '').replaceAll('-', '') : '';
    const textId = typeof uuid === 'string' && uuid.length > 0 && new TextEncoder().encode(uuid).length <= 30;
    if ((!textId && !/^[0-9a-f]{32}$/i.test(uuidHex)) || uuid.startsWith('REPLACE_'))
      throw Error('VLESS user ID must be your supplied UUID or text ID of 1 to 30 UTF-8 bytes. Replace any example value.');
    const serverName=outbound.streamSettings?.tlsSettings?.serverName;
    if (serverName && (typeof serverName !== 'string' || serverName.startsWith('REPLACE_')))
      throw Error('Replace the example TLS certificate hostname with the real server name.');
  }
  if (!['tcp','raw','ws',undefined].includes(outbound.streamSettings?.network) || outbound.streamSettings?.security !== 'tls')
    throw Error('Currently supported transports: TCP or WebSocket with TLS.');
  if (outbound.streamSettings.network === 'ws') {
    const ws=outbound.streamSettings.wsSettings ?? {}, path=ws.path ?? '/';
    if (typeof path !== 'string' || !path.startsWith('/') || path.length > 4096 || /[\x00-\x1f\x7f]/.test(path))
      throw Error('WebSocket path must start with / and contain no control characters.');
  }
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
function setImportMode(profile) {
  const form = $('xray-form');
  const replacing = Boolean(profile);
  const any = form.elements.carrier.querySelector('[value="Any"]');
  any.disabled = any.hidden = !replacing;
  if (!replacing) form.elements.carrier.value = 'MTN';
  $('replacement-enabled').hidden = !replacing;
  $('import-access').hidden = $('import-access').disabled = replacing;
  $('xray-title').textContent = replacing ? 'Replace imported profile' : 'Import connection JSON';
  $('import-submit').textContent = replacing ? 'Replace profile' : 'Import and generate code';
}
function resetImport() {
  $('xray-form').reset();
  $('xray-form').elements.id.value = '';
  setImportMode();
  $('import-feedback').textContent = '';
}
const importForm = $('xray-form');
const durationUnit = importForm.elements.unit;
durationUnit.onchange = () => {importForm.elements.duration.max = String(366 * 86400 / Number(durationUnit.value));};
$('xray-form').addEventListener('submit', e => {
  e.preventDefault();
  const form = e.target;
  busy(form, async () => {
    const data = new FormData(form);
    const id = data.get('id');
    checkImport(data.get('config'));
    const payload = {
      name: data.get('name'), carrier: data.get('carrier'), config: data.get('config'),
      allow_insecure: data.has('allow_insecure'), enabled: !id || data.has('enabled')
    };
    if (!id) {
      payload.access = {
        kind: data.get('kind'),
        duration_seconds: Number(data.get('duration')) * Number(data.get('unit')),
        quota_bytes: Math.round(Number(data.get('quota')) * Number(data.get('quota_unit')))
      };
    }
    const result = await api(id ? 'xray-profiles/'+id : 'xray-profiles/import-with-access', id ? 'PUT' : 'POST', payload);
    resetImport();
    durationUnit.onchange();
    if (!id) {
      $('code-value').textContent = result.code;
      $('new-code').hidden = false;
      $('new-code').scrollIntoView({behavior:'smooth', block:'nearest'});
    }
    notice(id ? 'Profile replaced.' : 'Profile imported. Copy the activation code below.');
    await refresh();
  });
});
$('xray-reset').onclick = () => {resetImport();durationUnit.onchange();};
setImportMode();
