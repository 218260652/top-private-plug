'use strict';

const $ = id => document.getElementById(id);
const message = text => { $('message').textContent = text; if (text) $('message').scrollIntoView({ block: 'nearest' }); };
const fields = form => Object.fromEntries(new FormData(form));
const carriers = ['MTN', 'Telkom'];
let selected = '';
let selectedPlan = '';

async function request(path, data) {
  const response = await fetch('/admin/api/' + path, {
    method: data === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-TPP-Request': '1' },
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  if (response.status === 401) {
    $('login').hidden = false;
    $('dashboard').hidden = true;
    $('dashboardNav').hidden = true;
    selected = '';
    $('detail').hidden = true;
    clearTemporary();
  }
  let result;
  try { result = await response.json(); }
  catch { throw Error('The server is temporarily unavailable. Please try again.'); }
  if (!response.ok) throw Error(result.error || 'The request failed.');
  return result;
}

const customer = (path, data) => request('customers/' + path, data);

function safe(action) {
  return async event => {
    if (event) event.preventDefault();
    const target = event && event.currentTarget;
    if (target && target.getAttribute('aria-busy') === 'true') return;
    const button = event && (event.submitter || (target.tagName === 'BUTTON' ? target : null));
    const oldLabel = button && button.textContent;
    if (target) target.setAttribute('aria-busy', 'true');
    if (button) { button.disabled = true; button.textContent = 'Please wait…'; }
    message('');
    try { await action(event); }
    catch (error) { message(error.message); }
    finally {
      if (target) target.removeAttribute('aria-busy');
      if (button) { button.disabled = false; if (button.textContent === 'Please wait…') button.textContent = oldLabel; }
    }
  };
}

function row(target, value, action, buttonLabel) {
  const li = document.createElement('li');
  const text = document.createElement('span');
  text.textContent = value;
  li.append(text);
  if (action) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = buttonLabel;
    button.addEventListener('click', safe(action));
    li.append(' ', button);
  }
  target.append(li);
}

function date(timestamp) {
  return new Date(timestamp * 1000).toLocaleString();
}

function events(target, items) {
  target.replaceChildren();
  if (!items.length) row(target, 'No activity recorded yet.');
  for (const item of items) row(target, date(item.at) + ' · ' + item.action + ' · ' + item.actor + (item.subject ? ' · ' + item.subject : ''));
}

function clearTemporary() {
  $('temporary').hidden = true;
  $('temporary').replaceChildren();
}

function showPassword(value, label) {
  clearTemporary();
  $('temporary').textContent = 'Shown once. Share securely with the customer. ' + label + ': ' + value + ' ';
  const close = document.createElement('button');
  close.type = 'button';
  close.textContent = 'Hide password';
  close.addEventListener('click', clearTemporary);
  $('temporary').append(close);
  $('temporary').hidden = false;
  $('temporary').scrollIntoView({ block: 'nearest' });
}

async function overview() {
  const summary = await customer('overview');
  $('login').hidden = true;
  $('dashboard').hidden = false;
  $('dashboardNav').hidden = false;
  $('overview').replaceChildren();
  metric('Total customers',  + Object.values(summary.counts).reduce((a, b) => a + b, 0));
  for (const [key, count] of Object.entries(summary.counts)) metric(key.replaceAll('_', ' '), count);
  metric('Registered devices', summary.registered_devices);
  metric('Recent app heartbeats', summary.recent_client_heartbeats);
  metric('Live VPN connections', 'Not available', 'Gateway telemetry is not connected');
  metric('Database', summary.database);
  events($('events'), summary.events);
  $('planList').replaceChildren();
  if (!summary.plans.length) row($('planList'), 'No subscription plans yet. Add your first plan below.');
  for (const plan of summary.plans) {
    row($('planList'), plan.name + ' · ' + plan.days + ' days · ' + (plan.price_cents / 100).toFixed(2),
      () => {
        selectedPlan = plan.id;
        $('savePlan').textContent = 'Update plan';
        $('cancelPlan').hidden = false;
        for (const key of ['name', 'days', 'price_cents']) $('plan').elements[key].value = plan[key];
        $('plan').scrollIntoView({ block: 'nearest' });
      }, 'Edit');
  }
  $('networks').replaceChildren();
  for (const carrier of carriers) {
    const current = summary.networks.find(item => item.carrier === carrier);
    const form = document.createElement('form');
    form.className = 'network-card';
    const label = document.createElement('label');
    label.textContent = carrier + ' ';
    const select = document.createElement('select');
    select.add(new Option('Disabled / no profile', ''));
    for (const p of summary.profiles.filter(p => !p.insecure && [carrier, 'Any'].includes(p.carrier))) {
      select.add(new Option(p.name + (p.enabled ? '' : ' (import disabled)'), p.id));
    }
    select.value = current ? current.profile : '';
    label.append(select);
    const testedLabel = document.createElement('label');
    testedLabel.className = 'check';
    const tested = document.createElement('input');
    tested.type = 'checkbox';
    tested.checked = Boolean(current && current.tested);
    select.addEventListener('change', () => { tested.checked = false; });
    testedLabel.append(tested, ' Verified on a physical carrier SIM');
    const button = document.createElement('button');
    button.textContent = 'Save ' + carrier;
    form.append(label, testedLabel, button);
    form.addEventListener('submit', safe(async () => {
      await customer('network', { carrier, profile: select.value, tested: tested.checked });
      await overview();
      message('Network assignment saved.');
    }));
    $('networks').append(form);
  }
}

async function list() {
  const data = await customer('users?q=' + encodeURIComponent(fields($('search')).q));
  $('users').replaceChildren();
  $('searchCount').textContent = data.users.length + ' accounts shown';
  if (!data.users.length) row($('users'), fields($('search')).q ? 'No matching accounts. Try another username or name.' : 'No customer accounts yet. Create your first account to get started.');
  for (const user of data.users) row($('users'), user.username + ' · ' + user.status, () => detail(user.id), 'Manage');
}

async function detail(id) {
  clearTemporary();
  const data = await customer('user?id=' + encodeURIComponent(id));
  const user = data.user;
  selected = id;
  $('detail').hidden = false;
  $('customerTitle').textContent = user.username;
  $('customerSummary').textContent = user.status + ' · Started ' + date(user.starts) + ' · Expires ' + date(user.expires);
  $('detail').scrollIntoView({ block: 'start' });
  $('detail').focus({ preventScroll: true });
  const edit = $('edit').elements;
  for (const key of ['name', 'notes', 'device_limit']) edit[key].value = user[key];
  edit.expires.value = new Date(user.expires * 1000).toISOString().slice(0, 19);
  edit.state.value = user.state;
  $('resume').hidden = !['paused', 'suspended'].includes(user.state);
  $('pause').hidden = ['paused', 'suspended', 'revoked'].includes(user.state);
  $('suspend').hidden = ['suspended', 'revoked'].includes(user.state);
  $('renew').hidden = user.state === 'revoked';
  for (const element of edit) element.disabled = user.state === 'revoked';
  $('devices').replaceChildren();
  if (!data.devices.length) row($('devices'), 'No devices registered for this account.');
  for (const device of data.devices) {
    row($('devices'), device.id + ' · last seen ' + date(device.seen) + (device.revoked ? ' · revoked' : ''), device.revoked ? null : async () => {
      if (!confirm('Revoke this device?')) return;
      await customer('revoke-device', { id, device: device.id });
      await detail(id);
      await overview();
    }, 'Revoke device');
  }
  events($('history'), data.events);
}

$('login').addEventListener('submit', safe(async () => {
  try { await request('login', fields($('login'))); }
  finally { $('login').elements.password.value = ''; $('login').elements.otp.value = ''; }
  await overview();
  await list();
}));
$('logout').addEventListener('click', safe(async () => {
  await request('logout', {});
  location.reload();
}));
$('search').addEventListener('submit', safe(list));
$('create').addEventListener('submit', safe(async () => {
  const data = fields($('create'));
  data.days = Number(data.days);
  data.device_limit = 1;
  const result = await customer('create', data);
  $('create').reset();
  await list();
  await overview();
  showPassword(result.initial_password, 'Password');
}));
$('edit').addEventListener('submit', safe(async () => {
  const data = fields($('edit'));
  data.id = selected;
  data.device_limit = Number(data.device_limit);
  data.expires = Date.parse(data.expires + 'Z') / 1000;
  await customer('update', data);
  await detail(selected);
  await list();
  await overview();
  message('Customer settings saved.');
}));
async function lifecycle(action, extra = {}) {
  const id = selected;
  await customer('lifecycle', { id, action, ...extra });
  if (action === 'delete') {
    selected = '';
    $('detail').hidden = true;
    clearTemporary();
  } else await detail(id);
  await list();
  await overview();
  message('Account updated.');
}

$('renew').addEventListener('submit', safe(() => lifecycle('renew', { days: Number(fields($('renew')).days) })));
for (const action of ['pause', 'suspend', 'resume']) {
  $(action).addEventListener('click', safe(() => lifecycle(action)));
}
$('delete').addEventListener('click', safe(async () => {
  if (!confirm('Remove this account from the dashboard and revoke its access? The audit history will be retained.')) return;
  await lifecycle('delete');
}));

$('revoke').addEventListener('click', safe(async () => {
  if (!confirm('Permanently revoke this account and all its sessions?')) return;
  await customer('update', { id: selected, state: 'revoked' });
  await detail(selected);
  await list();
  await overview();
}));
$('reset').addEventListener('click', safe(async () => {
  if (!confirm('Reset the password and revoke existing sessions?')) return;
  showPassword((await customer('reset', { id: selected })).temporary_password, 'Temporary reset password');
}));
$('plan').addEventListener('submit', safe(async () => {
  const data = fields($('plan'));
  data.id = selectedPlan;
  data.days = Number(data.days);
  data.price_cents = Number(data.price_cents);
  await customer('plan', data);
  resetPlan();
  await overview();
  message('Subscription plan saved.');
}));

function resetPlan() {
  selectedPlan = '';
  $('plan').reset();
  $('savePlan').textContent = 'Save plan';
  $('cancelPlan').hidden = true;
}
$('cancelPlan').addEventListener('click', resetPlan);
function metric(label, value, hint) {
  const li = document.createElement('li');
  const title = document.createElement('span');
  title.textContent = label;
  const strong = document.createElement('strong');
  strong.textContent = value;
  li.append(title, strong);
  if (hint) { const small = document.createElement('small'); small.textContent = hint; li.append(small); }
  $('overview').append(li);
}
for (const link of document.querySelectorAll('#dashboardNav a')) {
  link.addEventListener('click', () => {
    for (const item of document.querySelectorAll('#dashboardNav a')) item.removeAttribute('aria-current');
    link.setAttribute('aria-current', 'location');
  });
}
overview().then(list).catch(error => {
  if (!$('login').hidden && error.message === 'Sign in to continue') return;
  message(error.message);
});
