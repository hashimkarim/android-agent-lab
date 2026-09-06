// Actual Electron/WebCodecs UI and desktop job queue; only the device transport is simulated.
const {_electron:electron}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const {pathToFileURL}=require('node:url');
const {execFileSync}=require('node:child_process');

(async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'aal-viewer-ui-'));
  const project=path.join(root,'Checkout app'),output='app/build/outputs/apk/debug/app.apk';
  await fs.mkdir(path.join(project,path.dirname(output)),{recursive:true});
  await fs.writeFile(path.join(project,output),'existing-apk');
  await fs.writeFile(path.join(project,'gradlew'),'#!/bin/sh\nprintf built > .built\nprintf built-apk > app/build/outputs/apk/debug/app.apk\n');
  const unbuilt=path.join(root,'New app');await fs.mkdir(unbuilt);
  await fs.writeFile(path.join(unbuilt,'gradlew'),'#!/bin/sh\nexit 0\n');
  const manual=path.join(root,'picked.apk');await fs.writeFile(manual,'filesystem-apk');
  const adb=path.join(root,'adb'),python=execFileSync('python3',['-c','import sys; print(sys.executable)'],{encoding:'utf8'}).trim();
  await fs.writeFile(adb,`#!${python}
import sys,os,json
from pathlib import Path
args=sys.argv[1:]
with Path(os.environ['UI_ADB_LOG']).open('a') as log: log.write(json.dumps(args)+'\\n')
if 'devices' in args: print('List of devices attached\\nui-phone device usb:1-2 model:Pixel_9 transport_id:1')
else: print('Success')
`,{mode:0o700});
  const wrapper=path.join(root,'python'),privateFile=path.join(root,'viewer-env.json');
  await fs.writeFile(wrapper,`#!${python}
import sys,os,json,time,signal
from pathlib import Path
if len(sys.argv)>1 and Path(sys.argv[1]).name=='video.py':
 data={k:os.environ[k] for k in ['ADB_LAB_LIBRARY_SOCKET','ADB_LAB_LIBRARY_KEY','ADB_COORD_TOKEN']}
 with open(os.open(os.environ['UI_VIEWER_ENV'],os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600),'w') as f: json.dump(data,f)
 print(json.dumps({'url':os.environ['UI_VIEWER_URL']}),flush=True)
 while True: time.sleep(1)
else: os.execv(${JSON.stringify(python)},[${JSON.stringify(python)},*sys.argv[1:]])
`,{mode:0o700});
  const {desktopLibrary}=await import('../../viewer/library.mjs');
  const {WebSocketServer}=await import(pathToFileURL(path.resolve(__dirname,'../../viewer/node_modules/ws/wrapper.mjs')));
  let publicRoot=path.resolve(__dirname,'../../.desktop-build/runtime/viewer/public');
  const inputs=[],uploads=[];
  let app,page;
  const server=http.createServer(async(req,res)=>{
    const reply=(code,value)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
    try {
      const files={'/':'index.html','/client.js':'client.js','/style.css':'style.css'};
      if(files[req.url]){res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript':req.url.endsWith('.css')?'text/css':'text/html');return res.end(await fs.readFile(path.join(publicRoot,files[req.url])));}
      if(req.url==='/favicon.ico'){res.writeHead(204);return res.end();}
      if(req.url==='/status')return reply(200,{serial:'ui-phone',control:true,width:64,height:128,maxFps:60,profile:'fast'});
      const chunks=[];for await(const chunk of req)chunks.push(chunk);
      if(req.url==='/devtools/install'){uploads.push(Buffer.concat(chunks).toString());return reply(200,{text:'Filesystem APK installed.'});}
      const env=JSON.parse(await fs.readFile(privateFile,'utf8'));
      const library=desktopLibrary({serial:'ui-phone',token:env.ADB_COORD_TOKEN},env);
      if(req.url==='/library')return reply(200,await library.call({action:'catalog'}));
      if(req.url==='/library/install')return reply(200,await library.call({action:'install',...JSON.parse(Buffer.concat(chunks))}));
      if(req.url.startsWith('/library/job/'))return reply(200,await library.call({action:'job',id:req.url.split('/').at(-1)}));
      reply(404,{error:'Unexpected test route'});
    }catch(error){reply(409,{error:error.message});}
  });
  const wss=new WebSocketServer({server}),streams=[];
  wss.on('connection',(socket,req)=>{
    if(req.url==='/control')return socket.on('message',data=>{const input=JSON.parse(data);inputs.push(input);if(input.id)socket.send(JSON.stringify({type:'input-result',id:input.id,ok:true}));});
    streams.push(socket);socket.send(JSON.stringify({type:'video',codec:0x68323634}));
    // One generated 64×128 blue H.264 frame (SPS/PPS + IDR), with no external media dependency.
    const packet=(flag,data)=>{const header=Buffer.alloc(9);header[0]=flag;return Buffer.concat([header,Buffer.from(data,'base64')]);};
    socket.send(packet(0,'AAAAAWdCwAvcQRsBEAAAAwAQAAAHiPFCuAAAAAFozg/I'));
    socket.send(packet(2,'AAAAAWWIhDoRigACMXHAAEPKOAAIBcnJyddddddddddddeAAAAABZQiIhDoRigACMXHAAEPKOAAIBcnJyddddddddddddeA='));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const env={...process.env,ADB_LAB_USER_DATA:path.join(root,'data'),ADB_COORD_STATE:path.join(root,'claims'),ADB_COORD_ADB:adb,
    ADB_LAB_PYTHON:wrapper,UI_ADB_LOG:path.join(root,'adb.jsonl'),UI_VIEWER_ENV:privateFile,UI_VIEWER_URL:`http://127.0.0.1:${server.address().port}/#key=${'a'.repeat(43)}`};
  delete env.ELECTRON_RUN_AS_NODE;
  const evidence=path.resolve(__dirname,'../../.lab/workspace-ui');await fs.mkdir(evidence,{recursive:true});
  try {
    const packaged=process.env.ADB_LAB_TEST_EXECUTABLE;
    app=await electron.launch({args:packaged?[]:[path.resolve(__dirname,'..')],executablePath:packaged||require('electron'),env,chromiumSandbox:true,timeout:30000});
    if(packaged)publicRoot=path.join(await app.evaluate(()=>process.resourcesPath),'runtime/viewer/public');
    const manager=await app.firstWindow();manager.setDefaultTimeout(20000);
    await manager.getByRole('heading',{name:'Pixel 9',exact:true}).waitFor();
    for(const [name,folder] of [['Checkout',project],['Unbuilt project',unbuilt]])await manager.evaluate(({name,path})=>window.lab.request('saveProject',{name,path}),{name,path:folder});
    const newWindow=app.waitForEvent('window');
    await manager.locator('#devices').getByRole('button',{name:'Open device',exact:true}).click();
    page=await newWindow;page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.waitForFunction(()=>Number(document.querySelector('#screen').dataset.framesRendered)>0);
    await page.locator('#cursor-mode').selectOption('none');
    await page.mouse.move(1,1);await page.waitForTimeout(50);inputs.length=0;
    const box=await page.locator('#screen').boundingBox(),x=box.x+box.width*.4,y=box.y+box.height*.4;
    await page.mouse.move(x,y,{steps:5});await page.mouse.move(x+15,y+15,{steps:10});await page.waitForTimeout(50);
    assert.equal(await page.locator('#screen').evaluate(e=>getComputedStyle(e).cursor),'default');
    assert.equal(await page.locator('#cursors').isHidden(),true);assert.equal(inputs.filter(i=>i.kind==='hover').length,0);
    await page.mouse.down();await page.mouse.move(x+25,y+50,{steps:8});
    assert.ok(inputs.some(i=>i.kind==='pointer'&&i.phase==='move'),'Moves must reach the device before release');
    assert.ok(!inputs.some(i=>i.phase==='up'));await page.mouse.up();
    await page.locator('#cursor-mode').selectOption('all');
    await page.mouse.move(x,y);await page.waitForFunction(()=>JSON.parse(document.querySelector('#cursors').dataset.markers||'[]').some(m=>m.shape==='circle'));
    const first=JSON.parse(await page.locator('#cursors').getAttribute('data-markers'))[0];
    await page.mouse.move(x+25,y+25,{steps:5});await page.waitForTimeout(50);
    const second=JSON.parse(await page.locator('#cursors').getAttribute('data-markers'))[0];assert.ok(second.x>first.x&&second.y>first.y);
    await page.locator('#cursor-mode').selectOption('agents');
    const now=Date.now();streams.at(-1).send(JSON.stringify({type:'activity',now,events:[{id:'agent',actor:'codex:test',kind:'pointer',phase:'hover',persistent:true,points:[32,64],at:now/1000}]}));
    await page.waitForFunction(()=>JSON.parse(document.querySelector('#cursors').dataset.markers||'[]').some(m=>m.shape==='arrow'));
    assert.equal(await page.locator('#screen').evaluate(e=>getComputedStyle(e).cursor),'default');
    await page.locator('#install-apk').click();await page.locator('#install-projects').getByRole('heading',{name:'Checkout',exact:true}).waitFor();
    assert.equal(await page.locator('#install-dialog').isVisible(),true);
    await page.locator('#install-projects').getByRole('heading',{name:'Unbuilt project',exact:true}).waitFor();
    await page.screenshot({path:path.join(evidence,'live-apk-picker.png')});
    const checkout=page.locator('#install-projects article').filter({has:page.getByRole('heading',{name:'Checkout',exact:true})});
    await checkout.getByRole('button',{name:'Install APK',exact:true}).click();
    await page.locator('#tool-title').filter({hasText:'Completed'}).waitFor();
    await assert.rejects(fs.stat(path.join(project,'.built')),{code:'ENOENT'});
    let commands=(await fs.readFile(path.join(root,'adb.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
    assert.ok(commands.some(c=>c.includes('install')&&c[c.indexOf('-s')+1]==='ui-phone'));
    await page.locator('#install-apk').click();await checkout.getByRole('button',{name:'Build & install',exact:true}).click();
    await page.locator('#install-dialog').waitFor({state:'hidden'});
    await page.locator('#tool-title').filter({hasText:'Build & install Checkout · Completed'}).waitFor();
    assert.equal(await fs.readFile(path.join(project,'.built'),'utf8'),'built');
    await page.locator('#install-apk').click();await page.locator('#install-saved article').first().getByRole('button',{name:'Install',exact:true}).waitFor();
    await page.locator('#install-search').fill('no matching app');assert.equal(await page.locator('#install-projects article').count(),0);
    const chooser=page.waitForEvent('filechooser');await page.locator('#install-browse').click();await (await chooser).setFiles(manual);
    await page.locator('#tool-output').filter({hasText:'Filesystem APK installed.'}).waitFor();assert.deepEqual(uploads,['filesystem-apk']);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({ui:'passed',checks:['real WebCodecs frame','native cursor without hover work','live drag before release','continuous circle and agent cursors','project APK picker','install existing output without building','build and install on live device','saved library','filesystem picker'],evidence}));
  }catch(error){
    if(page){await page.screenshot({path:path.join(evidence,'viewer-failure.png')}).catch(()=>{});console.error(await page.locator('#tool-panel').innerText());console.error(await page.locator('#install-status').innerText());}
    throw error;
  }finally {
    if(app)await app.close();for(const client of wss.clients)client.terminate();wss.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await fs.rm(root,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
