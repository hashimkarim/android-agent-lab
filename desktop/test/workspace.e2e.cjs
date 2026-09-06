// Real Electron renderer + IPC + Python jobs, using an isolated simulated ADB host.
// Run with a desktop session (or xvfb-run): npm run test:ui --prefix desktop
const {_electron:electron}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');

(async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'aal-workspace-ui-'));
  const project=path.join(root,'Sample app');await fs.mkdir(project);
  await fs.mkdir(path.join(project,'app'));
  await fs.writeFile(path.join(project,'settings.gradle.kts'),'rootProject.name = "Sample from repo"\ninclude(":app")\n');
  await fs.writeFile(path.join(project,'app/build.gradle.kts'),'plugins { id("com.android.application") }\nandroid { defaultConfig { applicationId = "com.example.app" } }\n');
  const sdk=path.join(root,'sdk');await fs.mkdir(path.join(sdk,'platform-tools'),{recursive:true});
  await fs.writeFile(path.join(project,'gradlew'),'#!/bin/sh\nmkdir -p app/build/outputs/apk/debug\nprintf test-apk > app/build/outputs/apk/debug/app-debug.apk\n');
  const adb=path.join(root,'adb');
  await fs.writeFile(adb,`#!/usr/bin/env python3
import sys
args=sys.argv[1:]
if 'devices' in args: print('List of devices attached\\nui-phone device usb:1-2 model:Pixel_9 transport_id:1')
elif 'services' in args: print('studio-test _adb-tls-pairing._tcp 192.168.1.10:40000')
elif 'pair' in args: sys.stdin.readline(); print('Successfully paired to 192.168.1.10:40000')
elif 'connect' in args: print('connected to 192.168.1.10:40001')
elif 'resolve-activity' in args: print('com.example.app/.MainActivity')
else: print('Success')
`,{mode:0o700});
  const env={...process.env,ANDROID_HOME:sdk,ADB_LAB_USER_DATA:path.join(root,'data'),ADB_COORD_STATE:path.join(root,'claims'),ADB_COORD_ADB:adb};delete env.ELECTRON_RUN_AS_NODE;
  const packaged=process.env.ADB_LAB_TEST_EXECUTABLE;
  const app=await electron.launch({args:packaged?[]:[path.resolve(__dirname,'..')],executablePath:packaged||require('electron'),env,chromiumSandbox:true,timeout:30000});
  const page=await app.firstWindow();page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const previousClipboard=await app.evaluate(({clipboard})=>clipboard.readText());let testClipboard;
  const evidence=path.resolve(__dirname,'../../.lab/workspace-ui');await fs.mkdir(evidence,{recursive:true});
  try {
    await page.getByRole('heading',{name:'Pixel 9',exact:true}).waitFor();
    await page.locator('#devices').getByRole('button',{name:'Rename',exact:true}).click();
    await page.locator('#name-value').fill('Daily phone');await page.locator('#name-form').getByRole('button',{name:'Save',exact:true}).click();
    await page.getByRole('heading',{name:'Daily phone',exact:true}).waitFor();
    await page.locator('#devices').getByRole('button',{name:'Lock for me'}).click();
    await page.getByText('Locked for you · persists when the app closes',{exact:true}).waitFor();
    await page.locator('#devices').getByRole('button',{name:'Unlock',exact:false}).click();
    await page.locator('#devices').getByText('Available',{exact:true}).waitFor();
    if(await page.locator('#new-emulator').isEnabled()){
      for(const label of ['Checkout tests','Agent sandbox']){
        await page.locator('#new-emulator').click();await page.locator('#name-value').fill(label);await page.locator('#name-form').getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('heading',{name:label,exact:true}).waitFor();
      }
      assert.equal(await page.locator('#emulators article').count(),2);
    }
    await page.screenshot({path:path.join(evidence,'devices.png'),fullPage:true});
    await page.locator('#add-phone').click();await page.waitForFunction(()=>document.querySelector('#qr-image').naturalWidth===260);
    await page.screenshot({path:path.join(evidence,'pairing.png')});
    await page.getByRole('button',{name:'Pairing code',exact:true}).click();await page.locator('#pair-ip').click();await page.locator('#pair-ip').fill('192.168.1.10');await page.locator('#pair-port').fill('40000');await page.locator('#pair-code').fill('123456');await page.locator('#pair-form').getByRole('button',{name:'Pair phone',exact:true}).click();await page.locator('#phone-status').filter({hasText:'Phone paired'}).waitFor();
    assert.equal(await page.locator('#connect-ip').inputValue(),'192.168.1.10');
    assert.equal(await page.locator('#connect-port').inputValue(),'');
    assert.equal(await page.locator('#manual-connect').getAttribute('open'),'');
    await page.locator('#pair-port').fill('40000');await page.locator('#connect-port').fill('40001');
    await page.locator('#connect-form').getByRole('button',{name:'Connect',exact:true}).click();
    await page.locator('#phone-status').filter({hasText:'connected to'}).waitFor();
    await page.locator('#pair-code').focus();await page.locator('#pair-ip').focus();
    assert.deepEqual(await page.locator('#pair-ip').evaluate(e=>[e.selectionStart,e.selectionEnd]),[10,12]);
    await page.locator('#pair-ip').evaluate(e=>{const data=new DataTransfer();data.setData('text','192.168.44.96:34651');e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));});
    assert.equal(await page.locator('#pair-ip').inputValue(),'192.168.44.96');assert.equal(await page.locator('#pair-port').inputValue(),'34651');
    await page.screenshot({path:path.join(evidence,'pairing-code.png')});
    await page.locator('#phone-dialog').getByRole('button',{name:'Close',exact:true}).click();
    await page.getByRole('button',{name:'Projects & APKs',exact:true}).click();
    await page.locator('#add-project').click();await page.locator('#project-name').fill('Sample project');await page.locator('#project-path').fill(project);await page.locator('#detect-project').click();
    await page.locator('#project-detected').filter({hasText:'com.example.app'}).waitFor();
    assert.equal(await page.locator('#project-task').inputValue(),'');
    assert.match(await page.locator('#project-task').getAttribute('placeholder'),/:app:assembleDebug/);
    assert.equal(await page.locator('#project-package').inputValue(),'');
    await page.screenshot({path:path.join(evidence,'project-detection.png'),fullPage:true});
    await page.getByRole('button',{name:'Save project',exact:true}).click();
    await page.getByRole('heading',{name:'Sample project',exact:true}).waitFor();await page.locator('#target').selectOption('ui-phone');
    await page.getByRole('button',{name:'Build & install',exact:true}).click();
    await page.locator('#jobs .badge').filter({hasText:'Completed'}).waitFor();
    assert.match(await page.locator('#jobs').innerText(),/Saved 1 APK/);
    await page.getByRole('button',{name:'Projects & APKs',exact:true}).click();await page.getByRole('heading',{name:'app-debug.apk',exact:true}).waitFor();
    await page.screenshot({path:path.join(evidence,'library.png'),fullPage:true});
    await page.locator('#projects').getByRole('button',{name:'Launch',exact:true}).click();await page.locator('#jobs .job').first().locator('.badge').filter({hasText:'Completed'}).waitFor();
    await page.screenshot({path:path.join(evidence,'jobs.png'),fullPage:true});
    await page.locator('#jobs .job').first().getByRole('button',{name:'Copy output',exact:true}).click();
    await page.locator('#notice').filter({hasText:'Job output copied.'}).waitFor();
    const copied=await app.evaluate(({clipboard})=>clipboard.readText());
    testClipboard=copied;
    assert.match(copied,/Launch Sample project · Completed/);assert.match(copied,/com.example.app\/\.MainActivity/);
    await page.locator('#jobs .job').first().getByRole('button',{name:'Remove',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('#jobs .job').length===1);
    await fs.writeFile(path.join(project,'gradlew'),'#!/bin/sh\nsleep 120 &\necho $! > .cancel-child\nwait\n');
    await page.getByRole('button',{name:'Projects & APKs',exact:true}).click();
    await page.getByRole('button',{name:'Build',exact:true}).click();
    let childPid;
    for(let attempt=0;attempt<50;attempt++){try{childPid=Number(await fs.readFile(path.join(project,'.cancel-child'),'utf8'));break;}catch{await new Promise(r=>setTimeout(r,100));}}
    assert.ok(childPid>1);
    assert.equal(await page.locator('#jobs .job').first().getByRole('button',{name:'Remove',exact:true}).count(),0);
    const runningId=await page.locator('#jobs .job').first().getAttribute('data-job');
    const removalError=await page.evaluate(async id=>{try{await window.lab.request('removeJob',{id});return '';}catch(e){return e.message;}},runningId);
    assert.match(removalError,/wait for it to finish/);
    await page.locator('#clear-jobs').click();
    await page.waitForFunction(()=>document.querySelectorAll('#jobs .job').length===1);
    assert.equal(await page.locator('#jobs .job').first().getAttribute('data-job'),runningId);
    await page.locator('#jobs .job').first().getByRole('button',{name:'Cancel',exact:true}).click();
    await page.locator('#jobs .job').first().locator('.badge').filter({hasText:'Cancelled'}).waitFor();
    try {const stat=await fs.readFile(`/proc/${childPid}/stat`,'utf8');assert.ok(stat.includes(') Z '),'Cancelled build left a running child');} catch(e) {if(e.code!=='ENOENT')throw e;}
    await page.locator('#clear-jobs').click();await page.locator('#jobs .empty').waitFor();
    assert.deepEqual(errors,[]);
    const saved=JSON.parse(await fs.readFile(path.join(root,'data/workspace.json'),'utf8'));
    assert.equal(saved.names['ui-phone'],'Daily phone');assert.equal(saved.projects[0].name,'Sample project');assert.equal(saved.apks.length,1);assert.deepEqual(saved.reservations,{});
    console.log(JSON.stringify({ui:'passed',checks:['USB discovery','rename','persistent lock/unlock','multiple emulator inventory','QR render','code pairing','automatic project detection','build and install','APK library','app launch','copy output','remove finished jobs','clear finished preserves running jobs','cancel process group'],evidence}));
  } catch(error) {
    await page.screenshot({path:path.join(evidence,'failure.png'),fullPage:true}).catch(()=>{});
    console.error(await page.locator('#phone-dialog').innerText());
    throw error;
  } finally {
    if(testClipboard)await app.evaluate(({clipboard},{before,ours})=>{if(clipboard.readText()===ours)clipboard.writeText(before);},{before:previousClipboard,ours:testClipboard}).catch(()=>{});
    await app.close();await fs.rm(root,{recursive:true,force:true});
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
