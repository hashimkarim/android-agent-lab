'use strict';
const {spawn} = require('node:child_process');
const crypto = require('node:crypto');
const path = require('node:path');
const QRCode = require('qrcode');

function createWorkspace({app, dialog, clipboard, rpc, environment, python, runtime, manager, sessions, update}) {
  const jobs = new Map();
  let qr, stopping = false;
  const active = serial => [...jobs.values()].some(j => j.running && j.serial === serial);
  const snapshot = () => ({jobs: [...jobs.values()].map(({child,token,owned,...job}) => job)});
  function kill(job) {
    if (!job?.running) return;
    job.cancelled = true;
    if (!job.child) return;
    try {process.kill(-job.child.pid, 'SIGTERM');} catch {}
    const timer = setTimeout(() => {try {process.kill(-job.child.pid, 'SIGKILL');} catch {}}, 3000);
    job.child.once('close', () => clearTimeout(timer));
    timer.unref();
  }
  async function deviceToken(serial, expectedToken) {
    const session = [...sessions.values()].find(s => s.serial === serial);
    if (expectedToken && session?.token!==expectedToken) throw Error('This desktop device session has ended or changed.');
    if (session) {await rpc({action:'check',serial,token:session.token});return {token:session.token,owned:false};}
    const reserved = await rpc({action:'reservationToken',serial});
    if (reserved.token) return {token:reserved.token,owned:false};
    const record = await rpc({action:'claim',serial,owner:`human:desktop:job-${crypto.randomUUID().slice(0,8)}`});
    return {token:record.token,owned:true};
  }
  async function start(data) {
    if (stopping) throw Error('Application is closing.');
    if (!['emulator','importApk','install','installOutput','build','buildInstall','launch','debug','logcat'].includes(data.action)) throw Error('Unknown job.');
    if ([...jobs.values()].some(j=>j.running && (data.action==='emulator' ? j.emulator===data.id : data.id && j.item===data.id))) throw Error('This item already has a job in progress.');
    if (data.serial && active(data.serial)) throw Error('This device already has a job in progress.');
    const id = crypto.randomUUID();
    // Register before asynchronous token acquisition to prevent duplicate jobs.
    const job = {id, item:data.id, emulator:data.action==='emulator'?data.id:undefined, serial:data.serial,
      label:data.label || data.action, running:true, log:'', state:'Starting', child:null};
    jobs.set(id, job);
    try {
      if (['install','installOutput','buildInstall','launch','debug','logcat'].includes(data.action)) {
        if (typeof data.serial !== 'string' || !data.serial) throw Error('Select a connected target device.');
        Object.assign(job, await deviceToken(data.serial,data.expectedToken));
      } else if (data.action === 'emulator') {
        const session = [...sessions.values()].find(s=>s.serial===data.serial);
        if (session) throw Error('Stop this device’s shared session before changing the emulator.');
        const reserved = await rpc({action:'reservationToken',serial:data.serial});
        job.token = reserved.token;
      }
      if (stopping || job.cancelled) throw Error('Job cancelled.');
      job.child = spawn(python, ['-u',path.join(runtime,'scripts/desktop_jobs.py')],
        {env:{...environment(),...(job.token?{ADB_COORD_TOKEN:job.token}:{})}, detached:true, stdio:['pipe','pipe','pipe']});
      job.state = 'Running';
      let updateTimer;
      const output = chunk => {
        job.log = (job.log+chunk.toString()).slice(-64000);
        if (!updateTimer) updateTimer=setTimeout(()=>{updateTimer=null;update();},100);
      };
      job.child.stdout.on('data',output);job.child.stderr.on('data',output);
      job.child.once('error',e=>output(e.message));
      job.child.once('close',async code=>{
        clearTimeout(updateTimer);
        // A timed-out wrapper can leave a Gradle worker behind. This process
        // group belongs solely to this job; finish its descendants too.
        try {process.kill(-job.child.pid,'SIGKILL');} catch {}
        job.state=job.cancelled?'Cancelled':code===0?'Completed':'Failed';
        if (job.owned) await rpc({action:'release',serial:job.serial,token:job.token}).catch(e=>{job.log+='\n'+e.message;});
        job.running=false;delete job.token;
        const marker=job.log.split('\n').findLast(line=>line.startsWith('@@result '));
        let message=`${job.label}: ${job.state.toLowerCase()}.`;
        if (code===0 && marker) {try {message=JSON.parse(marker.slice(9)).message || message;} catch {}}
        job.log=job.log.split('\n').filter(line=>!line.startsWith('@@result ')).join('\n');
        job.message=message;
        update({message,error:job.state==='Failed'});
      });
      job.child.stdin.on('error',()=>{});job.child.stdin.end(JSON.stringify(data));
      while (jobs.size>24) {const old=[...jobs.values()].find(j=>!j.running);if (!old) break;jobs.delete(old.id);}
      update();return {ok:true,id,message:`${job.label} started. Follow its output in Jobs.`};
    } catch (error) {
      jobs.delete(id);
      if (job.owned) await rpc({action:'release',serial:job.serial,token:job.token}).catch(()=>{});
      throw error;
    }
  }
  async function connectPaired(result, address, initialServices) {
    const host=address.replace(/:\d+$/,''), services=initialServices || [];
    const candidates=rows=>{
      let matches=rows.filter(s=>s.kind==='connect' && s.address.replace(/:\d+$/,'')===host);
      if(result.guid) matches=matches.filter(s=>s.name===result.guid ||
        (s.name.startsWith(result.guid+' (') && /^\(\d+\)$/.test(s.name.slice(result.guid.length+1))));
      const addresses=[...new Set(matches.map(s=>s.address))];
      // Without an advertised identity, only an unambiguous endpoint is safe.
      return result.guid ? addresses.slice(0,3) : addresses.length===1 ? addresses : [];
    };
    let addresses=candidates(services);
    if(!addresses.length) {
      try {addresses=candidates((await rpc({action:'discover'})).services);} catch {}
    }
    for(const connection of addresses) {
      try {
        await rpc({action:'connect',address:connection});
        return {...result,paired:true,connected:true,address:connection,message:'Phone paired and connected.'};
      } catch { /* A renamed Avahi service may leave an old port in the cache. */ }
    }
    return {...result,paired:true,connected:false,pairingAddress:address,
      message:'Phone paired. Enter its connection port from the main Wireless debugging screen below to finish connecting.'};
  }
  const actions = {
    networks: () => rpc({action:'networks'}),
    rename: data => rpc({action:'rename',kind:data.kind,id:data.id,name:data.name}),
    saveProject: data => rpc({...data,action:'saveProject'}),
    inspectProject: data => rpc({action:'inspectProject',path:data.path,task:data.task,javaHome:data.javaHome,sdkHome:data.sdkHome}),
    createEmulator: async data => {
      if (process.arch!=='x64') throw Error('Local Android emulators need Linux x86_64 and /dev/kvm. Physical devices also work on ARM64.');
      const row=await rpc({action:'createEmulator',name:data.name});
      return {ok:true,message:`${row.name} added. Press Start when you’re ready.`};
    },
    emulator: async data => {
      const status=await rpc({action:'status'}), row=status.emulators.find(e=>e.id===data.id);
      if (!row) throw Error('Emulator no longer exists.');
      if (data.operation==='delete') {
        const answer=await dialog.showMessageBox(manager(),{type:'warning',buttons:['Cancel','Delete emulator'],defaultId:0,cancelId:0,
          message:`Delete ${row.name}?`,detail:'This permanently deletes this emulator’s installed apps and Android data. Other emulators are kept.'});
        if (answer.response!==1) return {ok:true};
      }
      return start({action:'emulator',id:row.id,operation:data.operation,serial:row.serial,label:`${data.operation} ${row.name}`});
    },
    pickProject: async () => {
      const result=await dialog.showOpenDialog(manager(),{title:'Choose a Gradle project',properties:['openDirectory']});
      return {path:result.canceled?'':result.filePaths[0]};
    },
    importApk: async () => {
      const result=await dialog.showOpenDialog(manager(),{title:'Save APK to library',properties:['openFile'],filters:[{name:'Android package',extensions:['apk']}]});
      return result.canceled?{ok:true}:start({action:'importApk',path:result.filePaths[0],label:`Save ${path.basename(result.filePaths[0])}`});
    },
    forget: async data => {
      const answer=await dialog.showMessageBox(manager(),{type:'question',buttons:['Cancel','Remove'],defaultId:0,cancelId:0,
        message:'Remove this saved item?',detail:data.kind==='apks'?'The library’s copy will be deleted. The original APK is kept.':'The original project or device is kept.'});
      if (answer.response!==1) return {ok:true};
      if ([...jobs.values()].some(j=>j.running && j.item===data.id)) throw Error('Wait for this item’s job to finish first.');
      return rpc({action:'forget',kind:data.kind,id:data.id});
    },
    job: data => start({...data,action:data.operation,label:data.label}),
    cancelJob: data => {const job=jobs.get(data.id);if (job) kill(job);return {ok:true};},
    copyJob: data => {
      const job=jobs.get(data.id);if(!job) throw Error('This job is no longer in the list.');
      clipboard.writeText(`${job.label} · ${job.state}\n${job.message || ''}\n\n${job.log}`.trim());
      return {ok:true,message:'Job output copied.'};
    },
    removeJob: data => {
      const job=jobs.get(data.id);if(job?.running) throw Error('Cancel this job or wait for it to finish before removing it.');
      jobs.delete(data.id);update();return {ok:true};
    },
    clearJobs: () => {
      for(const [id,job] of jobs) if(!job.running) jobs.delete(id);
      update();return {ok:true};
    },
    scan: () => rpc({action:'discover'}),
    pair: async data => connectPaired(await rpc({action:'pair',address:data.address,code:data.code}),data.address),
    connect: data => rpc({action:'connect',address:data.address}),
    qrStart: async () => {
      qr={id:crypto.randomUUID(),name:`studio-${crypto.randomBytes(5).toString('hex')}`,password:crypto.randomBytes(16).toString('hex'),expires:Date.now()+180000,busy:false};
      return {id:qr.id,image:await QRCode.toDataURL(`WIFI:T:ADB;S:${qr.name};P:${qr.password};;`,{width:260,margin:3}),expires:qr.expires};
    },
    qrCancel: () => {qr=null;return {ok:true};},
    qrPoll: async data => {
      const current=qr;
      if (!current || current.id!==data.id || Date.now()>current.expires) return {expired:true};
      if (current.busy) return {waiting:true};
      current.busy=true;
      try {
        const discovery=await rpc({action:'discover'}), services=discovery.services;
        if (qr!==current || Date.now()>current.expires) return {expired:true};
        if(discovery.available===false) return {unavailable:true,message:discovery.message};
        const service=services.find(s=>s.kind==='pairing' && s.name===current.name);
        if (!service) return {waiting:true};
        const result=await rpc({action:'pair',address:service.address,code:current.password});
        if (qr===current) qr=null;
        return connectPaired(result,service.address,services);
      } finally {current.busy=false;}
    },
  };
  async function shutdown() {
    stopping=true;qr=null;
    for (const job of jobs.values()) kill(job);
    const deadline=Date.now()+6000;
    while ([...jobs.values()].some(j=>j.running) && Date.now()<deadline) await new Promise(r=>setTimeout(r,100));
  }
  return {actions,snapshot,active,shutdown};
}
module.exports = {createWorkspace};
