'use strict';
const http = require('node:http');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');

// Shared browser views reach the same desktop job queue through this private
// socket. Only an active desktop session can select library items for its device.
async function createLibraryService({sessions, workspace, rpc}) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'aal-library-'));
  await fs.chmod(directory, 0o700);
  const socket = path.join(directory, 'desktop.sock'), secret = crypto.randomBytes(32).toString('hex');
  const equal = (a,b) => {
    if(typeof a!=='string' || typeof b!=='string') return false;
    const left=Buffer.from(a),right=Buffer.from(b);
    return left.length===right.length && crypto.timingSafeEqual(left,right);
  };
  const server = http.createServer(async (req,res) => {
    const reply = (code,value) => {res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
    if (req.method!=='POST' || req.url!=='/' || !equal(req.headers['x-lab-library-key'],secret)) return reply(403,{error:'Desktop library access denied.'});
    try {
      const chunks=[];let size=0;
      for await (const chunk of req) {size+=chunk.length;if(size>16384)throw Error('Request too large.');chunks.push(chunk);}
      const data=JSON.parse(Buffer.concat(chunks));
      const current=[...sessions.values()].find(s=>s.serial===data.serial && equal(data.token,s.token));
      if(!current) return reply(409,{error:'This desktop device session has ended or changed.'});
      const session={serial:current.serial,token:current.token,name:current.name};
      await rpc({action:'checkSession',serial:session.serial,token:session.token});
      if(data.action==='catalog') return reply(200,{available:true,device:{serial:session.serial,name:session.name},...await rpc({action:'library'})});
      if(data.action==='job') {
        const job=workspace.snapshot().jobs.find(j=>j.id===data.id && j.serial===session.serial);
        if(!job) throw Error('This job is not available for this device.');
        return reply(200,job);
      }
      if(data.action!=='install' || !['apk','project','output'].includes(data.kind) || typeof data.id!=='string') throw Error('Choose a saved APK or project.');
      const library=await rpc({action:'library'});
      const row=(data.kind==='apk'?library.apks:library.projects).find(p=>p.id===data.id);
      if(!row) throw Error('This library item no longer exists. Refresh the picker.');
      if(data.kind==='output' && !row.outputs.some(o=>o.path===data.output)) throw Error('This APK output is no longer available. Refresh the picker.');
      const operation=data.kind==='apk'?'install':data.kind==='output'?'installOutput':'buildInstall';
      return reply(200,await workspace.actions.job({operation,id:row.id,output:data.kind==='output'?data.output:undefined,serial:session.serial,expectedToken:session.token,label:`${data.kind==='project'?'Build & install':'Install'} ${row.name}`}));
    } catch(error) {reply(409,{error:error.message});}
  });
  server.requestTimeout=15000;server.headersTimeout=5000;
  try {
    await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(socket,resolve);});
    await fs.chmod(socket,0o600);
  } catch(error) {server.close();await fs.rm(directory,{recursive:true,force:true});throw error;}
  return {
    environment:()=>({ADB_LAB_LIBRARY_SOCKET:socket,ADB_LAB_LIBRARY_KEY:secret}),
    async close(){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await fs.rm(directory,{recursive:true,force:true});},
  };
}
module.exports={createLibraryService};
