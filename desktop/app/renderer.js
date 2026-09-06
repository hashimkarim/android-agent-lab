'use strict';
const $=id=>document.getElementById(id);
let state={devices:[],emulators:[],projects:[],apks:[],sessions:[],jobs:[]}, refreshing=false, claimDevice, nameAction, projectId, qrId, qrTimer, qrBusy=false, selectedProject, projectRevision=0;
const rendered={};
function notice(text,error=false) {$('notice').textContent=text;$('notice').className=error?'error':'';$('notice').hidden=!text;}
async function request(action,data={},target) {
  if (target) target.disabled=true;
  try {const result=await window.lab.request(action,data);if(result.message) notice(result.message);return result;}
  catch(e){const message=e.message.replace(/^Error invoking remote method '[^']+': Error: /,'');notice(message,true);for(const id of ['phone','project']) if($(id+'-dialog').open) $(id+'-status').textContent=message;}
  finally{if(target?.isConnected) target.disabled=false;}
}
function el(tag,text='',cls=''){const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;}
function button(text,action,cls='quiet'){const n=el('button',text,cls);n.onclick=()=>action(n);return n;}
function empty(text){return el('p',text,'empty');}
function page(name){for(const tab of document.querySelectorAll('[data-page]')){const selected=tab.dataset.page===name;tab.setAttribute('aria-current',selected?'page':'false');$('page-'+tab.dataset.page).hidden=!selected;}}
for(const tab of document.querySelectorAll('[data-page]')) tab.onclick=()=>page(tab.dataset.page);
const sessionFor=serial=>state.sessions.find(s=>s.serial===serial);
const deviceName=serial=>state.devices.find(d=>d.serial===serial)?.name || state.emulators.find(e=>e.serial===serial)?.name || serial;
const busy=serial=>state.jobs.some(j=>j.running && j.serial===serial);
function named(title,value,action){nameAction=action;$('name-title').textContent=title;$('name-value').value=value;$('name-dialog').showModal();$('name-value').select();}
async function rename(kind,id,value){named('Rename',value,async name=>{const result=await request('rename',{kind,id,name});if(result){$('name-dialog').close();await refresh();}});}
async function openDevice(device,token,target){
  const result=await request('start',{serial:device.serial,name:device.name,token,reclaim:device.claim?.expired===true,port:Number($('port').value),profile:$('profile').value},target);
  if(result) notice('Device opened. Share its browser URL or agent instructions from the session card.');
  await refresh();
}
function openButton(device){
  const session=sessionFor(device.serial),claimed=device.claim&&!device.claim.expired&&!device.lockedHere;
  const b=button(session?'Open window':claimed?'Join owner':device.claim?.expired?'Reclaim & open':'Open device',target=>{
    if(session) return request('reopen',{id:session.id},target);
    if(claimed){claimDevice=device;$('claim-description').textContent=`${device.name} is in use by ${device.claim.owner}.`;$('claim-token').value='';$('claim-dialog').showModal();}
    else openDevice(device,undefined,target);
  },'');
  b.disabled=device.state!=='device'||Boolean(device.claim?.reserved&&!device.lockedHere)||busy(device.serial);
  return b;
}
function lockButton(device){
  const session=sessionFor(device.serial);
  const b=button(device.lockedHere?'🔓 Unlock':device.claim?.expired?'Reclaim & lock':'🔒 Lock for me',async target=>{if(await request('reservation',{serial:device.serial,enabled:!device.lockedHere,reclaim:device.claim?.expired===true},target)) await refresh();});
  b.disabled=busy(device.serial)||Boolean(device.claim&&!device.claim.expired&&!device.lockedHere&&!session?.owned);
  return b;
}
function ownership(device){return device.lockedHere?'Locked for you · persists when the app closes':device.claim?.reserved?'Locked by its owner':device.claim&&!device.claim.expired?`In use by ${device.claim.owner}`:device.claim?`Expired claim · ${device.claim.owner}`:'Available';}
function renderDevices(){
  const devices=state.devices.filter(d=>!state.emulators.some(e=>e.serial===d.serial));$('devices').replaceChildren();
  if(!devices.length) $('devices').append(empty('Plug in a phone with USB debugging enabled, or use Add phone to pair over Wi-Fi.'));
  for(const d of devices){const card=el('article','','device');card.append(el('span',`${d.transport} · ${d.state==='device'?'Connected':d.state}`,'badge'+(d.state==='device'?'':' offline')),el('h3',d.name),el('p',d.serial,'serial'),el('p',ownership(d),'ownership'));
    const row=el('div','','button-row');row.append(openButton(d),button('Rename',()=>rename('device',d.serial,d.name)),lockButton(d));card.append(row);
    if(d.state==='unauthorized') card.append(el('p','Unlock the phone and allow USB debugging.','fine'));
    if(d.state==='no permissions') card.append(el('p','Install your distribution’s Android USB/udev rules, then reconnect the data cable.','fine'));
    if(['offline','disconnected'].includes(d.state) && splitAddress(d.serial)) {card.append(el('p','Wake the device and check its current IP and connection port in Wireless debugging.','fine'),button('Update connection…',()=>openPhone(d.serial),'quiet small'));}
    if(d.state==='disconnected') card.append(button('Forget saved name',async target=>{if(await request('forget',{kind:'device',id:d.serial},target)) refresh();},'quiet small'));
    $('devices').append(card);
  }
  $('emulators').replaceChildren();
  if(!state.emulators.length) $('emulators').append(empty('Create an emulator for each app, agent, or test environment. Each keeps its own Android data.'));
  for(const e of state.emulators){const d=state.devices.find(d=>d.serial===e.serial)||{...e,state:'disconnected'},running=e.state==='running',job=state.jobs.find(j=>j.running&&j.emulator===e.id);
    const card=el('article','','device');card.append(el('span',job?'Working…':d.state==='device'?'Ready':running?'Running · connecting':e.state==='unknown'?'Status unavailable':'Stopped','badge'+(d.state==='device'?'':' offline')),el('h3',e.name),el('p',`Android 16 · ${e.serial}`,'serial'),el('p',ownership(e),'ownership'));
    const controls=el('div','','button-row'),start=button(running?'Connect':'Start',async target=>{if(running){if(await request('connect',{address:e.serial},target)) refresh();}else if(await request('emulator',{id:e.id,operation:'start'},target)) refresh();},'');
    start.disabled=Boolean(job)||Boolean(e.claim&&!e.lockedHere);
    controls.append(d.state==='device'?openButton({...d,name:e.name}):start,button('Rename',()=>rename('emulators',e.id,e.name)),lockButton(e));card.append(controls);
    const more=el('div','','button-row secondary-actions');
    for(const [text,operation] of [['Stop','stop'],['Delete…','delete']]){const b=button(text,async target=>{if(await request('emulator',{id:e.id,operation},target)) refresh();},operation==='delete'?'danger small':'quiet small');b.disabled=Boolean(job)||Boolean(sessionFor(e.serial))||Boolean(e.claim&&!e.lockedHere)||(operation==='delete'&&e.lockedHere)||(operation==='stop'&&!running);more.append(b);}
    card.append(more);if(sessionFor(e.serial)) card.append(el('p','Stop the shared session before stopping or deleting Android.','fine'));$('emulators').append(card);
  }
}
function renderSessions(){
  $('sessions-section').hidden=!state.sessions.length;$('sessions').replaceChildren();
  for(const s of state.sessions){const card=el('article','','session');card.append(el('h3',deviceName(s.serial)),el('p',`${s.status}${s.locked?' · Locked for you':''}`));const actions=el('div','','session-actions');
    for(const [text,action] of [['Open window','reopen'],['Copy browser URL','copyUrl'],['Copy agent instructions','copyAgent'],['Stop session','stop']]){const b=button(text,async target=>{if(await request(action,{id:s.id},target)) refresh();},action==='stop'?'danger':'quiet');b.disabled=!s.status.startsWith('Live')||(action==='copyAgent'&&s.locked)||busy(s.serial);actions.append(b);}
    card.append(actions,el('p',s.locked?'The reservation stays locked after this session closes.':s.owned?'Stopping releases this session’s claim. Android stays running.':'Using another owner’s claim; closing keeps it intact.','fine'));$('sessions').append(card);
  }
}
function job(operation,id,label,target){const serial=$('target').value;if(['install','buildInstall','launch','debug','logcat'].includes(operation)&&!serial){notice('Select a connected target device first.',true);return;}
  return request('job',{operation,id,label,serial:['build','importApk'].includes(operation)?undefined:serial},target).then(result=>{if(result){page('jobs');refresh();}});
}
let detectionRevision=0;
async function detectProject(target) {
  const revision=++detectionRevision,path=$('project-path').value.trim();if(!path)return;
  const values={path};for(const key of ['task','javaHome','sdkHome']) values[key]=$('project-'+key).value.trim();
  $('project-detected').textContent='Reading project settings…';
  const config=await request('inspectProject',values,target);
  if(revision!==detectionRevision || !$('project-dialog').open || $('project-path').value.trim()!==path)return;
  if(!config){$('project-detected').textContent='';return;}
  $('project-name').placeholder=config.name;
  for(const key of ['task','package','javaHome','sdkHome']) $('project-'+key).placeholder=`Automatic · ${config[key] || (key==='package'?'available after building':'not found')}`;
  $('project-tasks').replaceChildren(...config.tasks.map(task=>new Option(task,task)));
  $('project-detected').textContent=[`Gradle ${config.gradleVersion||'wrapper'} · ${config.task}`,
    config.package?`App: ${config.package}`:'App ID: determined after building',
    `Java ${config.javaVersion||'?'}: ${config.javaHome||'not found'}`,
    `SDK: ${config.sdkHome||'not found'}`, ...config.issues].join('\n');
  $('project-status').textContent='';
}
function editProject(p={}){detectionRevision++;projectId=p.id;$('project-title').textContent=p.id?'Project settings':'Save a project';for(const key of ['name','path','task','package','apk','javaHome','sdkHome']) $('project-'+key).value=p.auto?.includes(key)?'':p[key]||'';$('project-status').textContent='';$('project-detected').textContent='';$('project-toolchain').open=false;$('project-dialog').showModal();if(p.path)detectProject();}
function renderLibrary(){
  const selected=$('target').value;$('target').replaceChildren(new Option('Select a connected device…',''));
  for(const d of state.devices.filter(d=>d.state==='device')) $('target').append(new Option(`${d.name} · ${d.serial}${d.claim?.reserved?' · Locked':''}`,d.serial));
  if([...$('target').options].some(o=>o.value===selected)) $('target').value=selected;
  $('projects').replaceChildren();if(!state.projects.length) $('projects').append(empty('Save a Gradle project to build, install, launch and inspect its app from here.'));
  for(const p of state.projects){const card=el('article','','panel library-item'+(p.id===selectedProject?' selected-project':''));card.dataset.project=p.id;card.tabIndex=-1;card.append(el('h3',p.name),el('p',p.path,'serial'),el('p',`${p.task} · ${p.apk||'Discover APK outputs'}`,'fine'));const actions=el('div','','button-row');
    for(const [text,op] of [['Build','build'],['Build & install','buildInstall'],['Launch','launch']]){const b=button(text,target=>job(op,p.id,`${text} ${p.name}`,target),op==='buildInstall'?'':'quiet');b.disabled=state.jobs.some(j=>j.running&&j.item===p.id);actions.append(b);}
    const more=el('details'),summary=el('summary','Project actions');more.append(summary);const secondary=el('div','','button-row');
    for(const [text,op] of [['Debug launch','debug'],['App logs','logcat']]){const b=button(text,target=>job(op,p.id,`${text} · ${p.name}`,target));b.disabled=state.jobs.some(j=>j.running&&j.item===p.id);secondary.append(b);}
    secondary.append(button('Edit settings',()=>editProject(p)),button('Remove…',async target=>{if(await request('forget',{kind:'projects',id:p.id},target)) refresh();},'danger'));more.append(secondary);card.append(actions,more);$('projects').append(card);
  }
  $('apks').replaceChildren();if(!state.apks.length) $('apks').append(empty('Save an APK, or build a project. Original APK files are kept when you remove library copies.'));
  for(const a of [...state.apks].reverse()){const card=el('article','','panel library-item');card.append(el('h3',a.name),el('p',`${(a.size/1048576).toFixed(1)} MB · ${new Date(a.savedAt*1000).toLocaleString()}`,'fine'),el('p',a.source,'serial'));const actions=el('div','','button-row');actions.append(button('Install',target=>job('install',a.id,`Install ${a.name}`,target),''),button('Rename',()=>rename('apks',a.id,a.name)),button('Remove…',async target=>{if(await request('forget',{kind:'apks',id:a.id},target)) refresh();},'danger'));card.append(actions);$('apks').append(card);}
}
function renderJobs(){
  const open=new Set([...$('jobs').querySelectorAll('details[open]')].map(n=>n.dataset.id));$('jobs').replaceChildren();
  $('job-count').textContent=state.jobs.filter(j=>j.running).length||'';
  $('clear-jobs').disabled=!state.jobs.some(j=>!j.running);
  if(!state.jobs.length) $('jobs').append(empty('Emulator startup, APK installs and build output will appear here.'));
  for(const job of [...state.jobs].reverse()){const card=el('article','','panel job');card.dataset.job=job.id;const heading=el('div','','dialog-heading');heading.append(el('h3',job.label),el('span',job.state,'badge'+(job.state==='Failed'?' offline':'')));card.append(heading);
    const actions=el('div','','button-row');actions.append(button('Copy output',target=>request('copyJob',{id:job.id},target),'quiet small'));
    if(job.running)actions.append(button('Cancel',target=>request('cancelJob',{id:job.id},target),'danger small'));
    else actions.append(button('Remove',target=>request('removeJob',{id:job.id},target),'quiet small'));
    card.append(actions);const details=el('details');details.dataset.id=job.id;details.open=open.has(job.id)||job.running||job.state==='Failed';details.append(el('summary','Output'),el('pre',job.log||'Waiting for output…'));card.append(details);$('jobs').append(card);}
}
function render(){
  for(const [key,values,fn] of [['devices',[state.devices,state.emulators,state.sessions,state.jobs.map(j=>[j.running,j.serial,j.emulator])],renderDevices],['sessions',[state.sessions,state.devices,state.jobs.map(j=>[j.running,j.serial])],renderSessions],['library',[selectedProject,state.projects,state.apks,state.devices,state.jobs.map(j=>[j.running,j.item])],renderLibrary],['jobs',state.jobs,renderJobs]]){const value=JSON.stringify(values);if(rendered[key]!==value){rendered[key]=value;fn();}}
}
function update(value){
  const {projectOpened,...snapshot}=value;Object.assign(state,snapshot);
  if(projectOpened){
    projectRevision++;selectedProject=projectOpened.id;
    state.projects=[...state.projects.filter(p=>p.id!==projectOpened.id),projectOpened];page('library');
  }
  render();
  if(projectOpened){const card=[...$('projects').children].find(n=>n.dataset.project===selectedProject);card?.scrollIntoView({block:'center'});card?.focus({preventScroll:true});}
  if(value.message){notice(value.message,value.error===true);refresh();}
}
async function refresh(){if(refreshing)return;refreshing=true;const revision=projectRevision;try{const value=await request('status');if(!value)return;if(revision!==projectRevision)delete value.projects;Object.assign(state,value);$('requirements').textContent=value.adb?'ADB ready · USB devices detected automatically':value.error||'Install Android platform-tools to connect devices.';$('version').textContent=`Android Agent Lab ${value.version}`;$('new-emulator').disabled=!(value.architecture==='x86_64'&&value.docker&&value.kvm);$('new-emulator').title=$('new-emulator').disabled?'Requires Docker, Linux x86_64 and read/write access to /dev/kvm':'';render();}finally{refreshing=false;}}
$('refresh').onclick=refresh;$('docs').onclick=()=>request('docs');$('skill').onclick=()=>request('installSkill',{},$('skill'));
$('new-emulator').onclick=()=>named('Create Android 16 emulator',`Android 16 · ${state.emulators.length+1}`,async name=>{if(await request('createEmulator',{name})){$('name-dialog').close();refresh();}});
$('name-form').onsubmit=e=>{e.preventDefault();nameAction($('name-value').value.trim());};
$('claim-form').onsubmit=e=>{e.preventDefault();const token=$('claim-token').value.trim();$('claim-token').value='';$('claim-dialog').close();openDevice(claimDevice,token);};
$('join-form').onsubmit=async e=>{e.preventDefault();if(await request('open',{url:$('join-url').value.trim()},e.submitter)) $('join-url').value='';};
$('profile').value=localStorage.getItem('adb-lab-profile')||'fast';$('profile').onchange=()=>localStorage.setItem('adb-lab-profile',$('profile').value);
$('import-apk').onclick=()=>request('importApk',{},$('import-apk')).then(refresh);$('add-project').onclick=()=>editProject();
$('browse-project').onclick=async()=>{const result=await request('pickProject');if(result?.path){$('project-path').value=result.path;detectProject();}};
$('project-path').onchange=()=>detectProject();$('detect-project').onclick=()=>detectProject($('detect-project'));
$('clear-jobs').onclick=()=>request('clearJobs');
$('project-form').onsubmit=async e=>{e.preventDefault();const values={id:projectId};for(const key of ['name','path','task','package','apk','javaHome','sdkHome'])values[key]=$('project-'+key).value.trim();if(await request('saveProject',values,e.submitter)){$('project-dialog').close();refresh();}};
for(const b of document.querySelectorAll('[data-close]')) b.onclick=()=>$(b.dataset.close).close();
function splitAddress(value) {
  const match=value.trim().match(/^(\[[^\]]+\]|[^:]+):(\d{1,5})$/);
  return match ? {ip:match[1].replace(/^\[|\]$/g,''),port:match[2]} : null;
}
function fillAddress(form,value) {
  const address=splitAddress(value);if(!address)return;
  $(form+'-ip').value=address.ip;$(form+'-port').value=address.port;
}
function addressValue(form) {
  const ip=$(form+'-ip').value.trim().replace(/^\[|\]$/g,'');
  return `${ip.includes(':')?'['+ip+']':ip}:${$(form+'-port').value}`;
}
for(const form of ['pair','connect']) {
  const input=$(form+'-ip');
  input.onfocus=()=>{
    const start=/^\d+\.\d+\.\d+\.\d*$/.test(input.value)?input.value.lastIndexOf('.')+1:0;
    input.setSelectionRange(start,input.value.length);
    input.addEventListener('mouseup',e=>e.preventDefault(),{once:true});
  };
  input.onpaste=e=>{
    const value=e.clipboardData.getData('text').trim(),address=splitAddress(value);
    if(address){e.preventDefault();fillAddress(form,value);$(form==='pair'?'pair-code':'connect-port').focus();}
    else if(/^\d+\.\d+\.\d+\.\d+$/.test(value) || /^[a-fA-F0-9:]+$/.test(value) && value.includes(':')) {
      e.preventDefault();input.value=value;$(form+'-port').focus();
    }
  };
}
let phoneNetworks=[];
async function loadNetworks() {
  const result=await request('networks');if(!result)return;phoneNetworks=result.networks;
  $('phone-network').replaceChildren(...phoneNetworks.map((n,i)=>new Option(`${n.kind} · ${n.address} (${n.interface})`,String(i))));
  $('network-label').hidden=!phoneNetworks.length;
  if(phoneNetworks.length) {
    for(const form of ['pair','connect']) if(!$(form+'-ip').value) $(form+'-ip').value=phoneNetworks[0].prefix;
    $('network-hint').textContent='The first three numbers are filled in from your laptop. Enter the device’s last number, or edit the whole address.';
  }
}
$('phone-network').onchange=()=>{
  const network=phoneNetworks[Number($('phone-network').value)];if(!network)return;
  for(const form of ['pair','connect']) {
    const input=$(form+'-ip'),last=/^\d+\.\d+\.\d+\.(\d*)$/.exec(input.value)?.[1]||'';
    input.value=network.prefix+last;
  }
  $('pair-ip').focus();
};
function connectTab(name) {
  for(const tab of document.querySelectorAll('[data-connect]')) {
    const selected=tab.dataset.connect===name;tab.setAttribute('aria-current',selected?'page':'false');$('connect-'+tab.dataset.connect).hidden=!selected;
  }
  if(name==='qr')newQr();
  else {clearInterval(qrTimer);request('qrCancel');if(name==='code')scan();}
}
function openPhone(address) {
  $('phone-status').textContent='';$('phone-dialog').showModal();loadNetworks();
  if(address) {fillAddress('connect',address);connectTab('code');$('manual-connect').open=true;$('connect-port').focus();}
  else connectTab('qr');
}
function paired(result) {
  if(result.address)fillAddress('connect',result.address);
  else if(result.pairingAddress) $('connect-ip').value=splitAddress(result.pairingAddress)?.ip||$('pair-ip').value;
  $('phone-status').textContent=result.message;
  if(!result.connected){connectTab('code');$('manual-connect').open=true;$('connect-port').focus();}
  refresh();
}
async function newQr() {
  clearInterval(qrTimer);$('qr-status').textContent='Preparing QR code…';
  const result=await request('qrStart');if(!result || !$('phone-dialog').open || $('connect-qr').hidden)return;
  qrId=result.id;$('qr-image').src=result.image;$('qr-status').textContent='Waiting for your phone · expires in 3 minutes';
  qrTimer=setInterval(async()=>{
    if(qrBusy)return;qrBusy=true;
    try {
      const reply=await request('qrPoll',{id:qrId});
      if(reply?.paired||reply?.expired||reply?.unavailable){
        clearInterval(qrTimer);$('qr-status').textContent=reply.unavailable?reply.message:reply.paired?reply.message:'QR expired. Generate a new code to try again.';
        if(reply.paired && $('phone-dialog').open)paired(reply);
      }
    }finally{qrBusy=false;}
  },2000);
}
$('add-phone').onclick=()=>openPhone();$('qr-new').onclick=newQr;
$('phone-dialog').onclose=()=>{clearInterval(qrTimer);request('qrCancel');$('qr-image').removeAttribute('src');};
for(const b of document.querySelectorAll('[data-connect]'))b.onclick=()=>connectTab(b.dataset.connect);
async function scan() {
  const result=await request('scan',{},$('scan'));if(!result)return;$('nearby').replaceChildren();
  if(!result.services.length)$('nearby').append(el('p',result.message||'No devices advertising yet. Keep Wireless debugging open, or enter its address below.','fine'));
  for(const service of result.services) {
    const b=button(`${service.kind==='pairing'?'Pair':'Connect'} · ${service.address}`,async target=>{
      if(service.kind==='pairing'){fillAddress('pair',service.address);$('pair-code').focus();}
      else {fillAddress('connect',service.address);$('manual-connect').open=true;const connected=await request('connect',{address:service.address},target);if(connected)$('phone-status').textContent=connected.message;refresh();}
    });$('nearby').append(b);
  }
}
$('scan').onclick=scan;
$('pair-form').onsubmit=async e=>{
  e.preventDefault();const address=addressValue('pair');$('phone-status').textContent='Pairing and finding the connection port…';
  const result=await request('pair',{address,code:$('pair-code').value},e.submitter);$('pair-code').value='';
  if(result)paired(result);
};
$('connect-form').onsubmit=async e=>{e.preventDefault();const result=await request('connect',{address:addressValue('connect')},e.submitter);if(result){$('phone-status').textContent=result.message;refresh();}};
$('usb-refresh').onclick=async()=>{await refresh();const devices=state.devices.filter(d=>d.transport==='USB');$('usb-status').textContent=devices.length?devices.map(d=>`${d.name} · ${d.state}`).join('\n'):'No USB device detected yet. Check the cable and debugging prompt.';};
window.lab.onUpdate(update);refresh().then(()=>request('ready'));setInterval(()=>{if(!document.hidden)refresh();},3000);
