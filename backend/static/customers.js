'use strict';

const $ = id => document.getElementById(id);
const message = text => { $('message').textContent = text; };
const fields = form => Object.fromEntries(new FormData(form));
const carriers = ['MTN', 'Telkom', 'Cell C'];
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
    clearTemporary();
  }
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'The request failed.');
  return result;
}

const customer = (path, data) => request('customers/' + path, data);

function safe(action) {
  return async event => {
    if (event) event.preventDefault();
    message('');
    try { await action(event); }
    catch (error) { message(error.message); }
  };
}

function row(target, value, action, buttonLabel) {
  const li = document.createElement('li');
  li.textContent = value;
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
  for (const item of items) row(target, date(item.at) + ' · ' + item.action + ' · ' + item.actor + (item.subject ? ' · ' + item.subject : ''));
}

function clearTemporary() {
  $('temporary').hidden = true;
  $('temporary').replaceChildren();
}

function temporary(value) {
  clearTemporary();
  $('temporary').textContent = 'One-time display. Share securely with the customer. Temporary password: ' + value + ' ';
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
  $('overview').replaceChildren();
  row($('overview'), 'Total customers: ' + Object.values(summary.counts).reduce((a, b) => a + b, 0));
  for (const [key, count] of Object.entries(summary.counts)) row($('overview'), key + ': ' + count);
  row($('overview'), 'Registered devices: ' + summary.registered_devices);
  row($('overview'), 'Recent app heartbeats: ' + summary.recent_client_heartbeats);
  row($('overview'), 'Live VPN connections: gateway telemetry unavailable');
  row($('overview'), 'Database: ' + summary.database);
  events($('events'), summary.events);
  $('planList').replaceChildren();
  for (const plan of summary.plans) {
    row($('planList'), plan.name + ' · ' + plan.days + ' days · ' + (plan.price_cents / 100).toFixed(2),
      () => {
        selectedPlan = plan.id;
        for (const key of ['name', 'days', 'price_cents']) $('plan').elements[key].value = plan[key];
        $('plan').scrollIntoView({ block: 'nearest' });
      }, 'Edit');
  }
  $('networks').replaceChildren();
  for (const carrier of carriers) {
    const current = summary.networks.find(item => item.carrier === carrier);
    const form = document.createElement('form');
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
  for (const user of data.users) row($('users'), user.username + ' · ' + user.status, () => detail(user.id), 'Manage');
}

async function detail(id) {
  clearTemporary();
  const data = await customer('user?id=' + encodeURIComponent(id));
  const user = data.user;
  selected = id;
  $('detail').hidden = false;
  $('customerTitle').textContent = user.username + ' · ' + user.status + ' · starts ' + date(user.starts);
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
  temporary(result.temporary_password);
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
  temporary((await customer('reset', { id: selected })).temporary_password);
}));
$('plan').addEventListener('submit', safe(async () => {
  const data = fields($('plan'));
  data.id = selectedPlan;
  data.days = Number(data.days);
  data.price_cents = Number(data.price_cents);
  await customer('plan', data);
  selectedPlan = '';
  $('plan').reset();
  await overview();
}));

overview().then(list).catch(error => {
  if (!$('login').hidden && error.message === 'Sign in to continue') return;
  message(error.message);
});
