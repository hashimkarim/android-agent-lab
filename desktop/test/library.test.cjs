const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const {createLibraryService}=require('../app/library.cjs');
const {createWorkspace}=require('../app/workspace.cjs');

test('browser library requests stay on the live device and revoke with its claim',async()=>{
  const {desktopLibrary}=await import('../../viewer/library.mjs');
  const sessions=new Map([['first',{serial:'phone',name:'Daily phone',token:'first-token'}]]), jobs=[];
  let revoked=false;
  const rpc=async data=>{
    if(data.action==='checkSession'){if(revoked)throw Error('Claim changed');return {};}
    assert.equal(data.action,'library');
    return {projects:[{id:'project',name:'My app',outputs:[{path:'app/build/outputs/apk/debug/app.apk'}]}],apks:[{id:'apk',name:'Saved app'}]};
  };
  const service=await createLibraryService({sessions,rpc,workspace:{snapshot:()=>({jobs:[{id:'j1',serial:'phone'},{id:'j2',serial:'other'}]}),actions:{job:async data=>{jobs.push(data);return {id:'j1'};}}}});
  const env=service.environment(), client=desktopLibrary({serial:'phone',token:'first-token'},env);
  try {
    assert.equal((await fs.stat(env.ADB_LAB_LIBRARY_SOCKET)).mode&0o777,0o600);
    const catalog=await client.call({action:'catalog'});assert.equal(catalog.device.name,'Daily phone');
    await client.call({action:'install',kind:'project',id:'project',serial:'other',token:'wrong'});
    assert.equal(jobs[0].serial,'phone');assert.equal(jobs[0].expectedToken,'first-token');assert.equal(jobs[0].operation,'buildInstall');
    await client.call({action:'install',kind:'output',id:'project',output:'app/build/outputs/apk/debug/app.apk'});
    assert.equal(jobs[1].operation,'installOutput');
    await assert.rejects(client.call({action:'install',kind:'output',id:'project',output:'../../external.apk'}),/no longer available/);
    await assert.rejects(client.call({action:'install',kind:'apk',id:'missing'}),/no longer exists/);
    await assert.rejects(client.call({action:'job',id:'j2'}),/not available for this device/);
    assert.equal((await client.call({action:'job',id:'j1'})).serial,'phone');
    await assert.rejects(desktopLibrary({serial:'phone',token:'first-token'},{...env,ADB_LAB_LIBRARY_KEY:'wrong'}).call({action:'catalog'}),/access denied/);
    revoked=true;
    await assert.rejects(client.call({action:'install',kind:'apk',id:'apk'}),/Claim changed/);
    revoked=false;sessions.get('first').token='next-token';
    await assert.rejects(client.call({action:'catalog'}),/ended or changed/);
    assert.equal(jobs.length,2);
  }finally{await service.close();}
  await assert.rejects(fs.stat(env.ADB_LAB_LIBRARY_SOCKET),{code:'ENOENT'});
  assert.equal((await desktopLibrary({serial:'phone',token:'token'},{}).call({action:'catalog'})).available,false);
});

test('a session rotation during library lookup cannot grant a stale viewer a fresh job token',async()=>{
  const sessions=new Map([['s',{serial:'phone',token:'new-token'}]]),calls=[];
  const workspace=createWorkspace({sessions,rpc:async data=>{calls.push(data);}});
  try{
    await assert.rejects(workspace.actions.job({operation:'install',id:'apk',serial:'phone',expectedToken:'old-token'}),/ended or changed/);
    assert.deepEqual(workspace.snapshot().jobs,[]);assert.deepEqual(calls,[]);
  }finally{await workspace.shutdown();}
});
