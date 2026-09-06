// Actual process launches exercise cwd forwarding, startup queues and persistence.
const {_electron:electron}=require('playwright');
const assert=require('node:assert/strict');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const run=promisify(execFile);

(async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'aal-project-command-'));
  const first=path.join(root,'First app'),second=path.join(root,"Second app 'quoted' $(literal)");
  const alias=path.join(root,'Project alias');
  for(const project of [first,second]){
    await fs.mkdir(project);
    await fs.writeFile(path.join(project,'gradlew'),'#!/bin/sh\ntouch SHOULD_NOT_RUN\nexit 99\n');
  }
  await fs.symlink(first,alias);
  const adb=path.join(root,'adb');
  await fs.writeFile(adb,`#!/usr/bin/env python3
from pathlib import Path
import sys, time
if 'devices' not in sys.argv: raise SystemExit('This test must not run device operations')
marker = Path(__file__).with_name('discovered')
if not marker.exists():
    marker.touch()
    time.sleep(2)
print('List of devices attached')
`,{mode:0o700});
  const env={...process.env,ADB_LAB_USER_DATA:path.join(root,'data'),ADB_COORD_STATE:path.join(root,'claims'),ADB_COORD_ADB:adb};delete env.ELECTRON_RUN_AS_NODE;
  const executable=process.env.ADB_LAB_TEST_EXECUTABLE||require('electron');
  const prefix=process.env.ADB_LAB_TEST_EXECUTABLE?[]:[path.resolve(__dirname,'..')];
  const invoke=(args,cwd=root,extraEnv={})=>run(executable,[...prefix,...args],{cwd,env:{...env,...extraEnv},timeout:20000,maxBuffer:1024*1024});
  const launch=(args,cwd)=>electron.launch({executablePath:executable,args:[...prefix,...args],cwd,env,chromiumSandbox:true,timeout:30000});
  const evidence=path.resolve(__dirname,'../../.lab/workspace-ui');await fs.mkdir(evidence,{recursive:true});
  let app;
  try {
    app=await launch(['.'],first);
    let page=await app.firstWindow();page.setDefaultTimeout(20000);
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    // Launch while first discovery is pending, before the renderer is ready.
    assert.match((await invoke(['.'],second)).stdout,/Project request sent/);
    await page.locator('#projects article').filter({has:page.getByRole('heading',{name:'First app',exact:true})}).waitFor();
    await page.locator('#projects .selected-project h3').filter({hasText:path.basename(second)}).waitFor();
    assert.equal(await page.locator('#projects article').count(),2);
    assert.equal(app.windows().length,1);
    const firstCard=page.locator('#projects article').filter({has:page.getByRole('heading',{name:'First app',exact:true})});
    await firstCard.locator('summary').click();await firstCard.getByRole('button',{name:'Edit settings',exact:true}).click();
    await page.locator('#project-name').fill('My checkout');
    await page.locator('#project-task').fill(':app:assembleDemoDebug');
    await page.locator('#project-package').fill('com.example.demo');
    await page.locator('#project-apk').fill('app/build/outputs/apk/demo/debug/app.apk');
    await page.getByRole('button',{name:'Save project',exact:true}).click();
    await page.getByRole('heading',{name:'My checkout',exact:true}).waitFor();
    await page.getByRole('button',{name:'Devices',exact:true}).click();
    await invoke(['--project',alias],second);
    await page.locator('#projects .selected-project h3').filter({hasText:'My checkout'}).waitFor();
    assert.equal(await page.locator('#page-library').isVisible(),true);
    assert.equal(await page.locator('#projects article').count(),2);
    await page.screenshot({path:path.join(evidence,'project-command.png'),fullPage:true});
    await page.getByRole('button',{name:'Devices',exact:true}).click();
    const help=await invoke(['--help'],root,{DISPLAY:'',WAYLAND_DISPLAY:''});assert.match(help.stdout,/android-agent-lab \./);
    const version=await invoke(['--version']);assert.match(version.stdout.trim(),/^\d+\.\d+\.\d+$/);
    for(const args of [[root],[path.join(root,'missing')],['--project'],['--wrong']]) await assert.rejects(invoke(args),e=>e.code===2&&/Android Agent Lab:/.test(e.stderr));
    assert.equal(await page.locator('#page-devices').isVisible(),true);
    assert.equal(app.windows().length,1);
    assert.deepEqual(errors,[]);
    await app.close();app=null;
    // A fresh process should select the same entry and preserve all custom fields.
    app=await launch(['--project','Project alias'],root);
    page=await app.firstWindow();page.setDefaultTimeout(20000);
    await page.locator('#projects .selected-project h3').filter({hasText:'My checkout'}).waitFor();
    const status=await page.evaluate(()=>window.lab.request('status'));
    assert.equal(status.projects.length,2);assert.equal(status.jobs.length,0);assert.equal(status.apks.length,0);
    assert.deepEqual(status.projects.find(p=>p.path===first),{
      id:status.projects.find(p=>p.path===first).id,name:'My checkout',path:first,
      task:':app:assembleDemoDebug',package:'com.example.demo',apk:'app/build/outputs/apk/demo/debug/app.apk',
      auto:[],javaHome:'',sdkHome:''
    });
    for(const project of [first,second]) await assert.rejects(fs.stat(path.join(project,'SHOULD_NOT_RUN')),e=>e.code==='ENOENT');
    await fs.access(path.join(root,'data/skills/android-agent-lab-projects/SKILL.md'));
    console.log(JSON.stringify({projectCommand:'passed',checks:['cold start','queued second launch','caller cwd','quoted paths','symlink deduplication','saved settings','restart persistence','help without display','invalid arguments','no builds or device actions'],evidence}));
  } finally {if(app)await app.close();await fs.rm(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
