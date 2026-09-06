// Library selection shares the desktop queue; file selection stays browser-native.
export function createInstaller(api, device, followJob) {
  const $=id=>document.getElementById(id), dialog=$('install-dialog');
  let library, loading=false, submitting=false, generation=0;
  const element=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
  const button=(text,action)=>{const node=element('button',text);node.onclick=action;node.disabled=submitting;return node;};
  async function install(data) {
    if(submitting)return;submitting=true;render();$('install-status').textContent='Starting install…';
    try {const result=await api('/library/install',data);dialog.close();followJob(result.id);}
    catch(error){$('install-status').textContent=error.message;}
    finally{submitting=false;render();}
  }
  function render() {
    const projects=$('install-projects'),apks=$('install-saved');projects.replaceChildren();apks.replaceChildren();
    if(!library)return;
    const query=$('install-search').value.trim().toLowerCase();
    const matches=row=>`${row.name} ${row.path||''} ${row.source||''}`.toLowerCase().includes(query);
    for(const project of library.projects.filter(matches)) {
      const card=element('article','','install-item');card.append(element('h3',project.name),element('p',project.path,'apk-path'));
      const choices=[...library.apks.filter(a=>a.project===project.id).map(a=>({label:`Saved · ${a.name}`,at:a.savedAt,data:{kind:'apk',id:a.id}})),
        ...(project.outputs||[]).map(o=>({label:`Project output · ${o.path}`,at:o.modified,data:{kind:'output',id:project.id,output:o.path}}))].sort((a,b)=>b.at-a.at);
      const controls=element('div','','install-actions');
      if(choices.length){
        const select=element('select');select.setAttribute('aria-label',`APK for ${project.name}`);
        choices.forEach((choice,i)=>select.append(new Option(choice.label,String(i))));
        controls.append(select,button('Install APK',()=>install(choices[Number(select.value)].data)));
      } else card.append(element('p',`Ready to build · ${project.task}`,'muted'));
      controls.append(button('Build & install',()=>install({kind:'project',id:project.id})));card.append(controls);projects.append(card);
    }
    for(const apk of [...library.apks].sort((a,b)=>b.savedAt-a.savedAt).filter(matches)) {
      const card=element('article','','install-item saved-apk');const text=element('div');text.append(element('h3',apk.name),element('p',`${(apk.size/1048576).toFixed(1)} MB · ${new Date(apk.savedAt*1000).toLocaleString()}`,'muted'));
      card.append(text,button('Install',()=>install({kind:'apk',id:apk.id})));apks.append(card);
    }
    if(!projects.children.length)projects.append(element('p',query?'No matching projects.':'Add a Gradle project with android-agent-lab . to build and install it here.','picker-empty'));
    if(!apks.children.length)apks.append(element('p',query?'No matching saved APKs.':'APKs saved or built in the app will appear here.','picker-empty'));
  }
  async function load() {
    if(loading)return;loading=true;const request=++generation;$('install-status').textContent='Loading your library…';
    try {
      const result=await api('/library');if(request!==generation)return;library=result;
      $('install-target').textContent=`Install on ${result.device?.name || device()}`;
      $('install-status').textContent=result.available?'Choose an APK, or build a project for this device.':'Open this device from Android Agent Lab to use saved projects. You can browse for an APK below.';
      render();
    } catch(error){if(request===generation)$('install-status').textContent=`${error.message} You can still browse for an APK.`;}
    finally{loading=false;}
  }
  $('install-search').oninput=render;$('install-library-refresh').onclick=load;
  $('install-close').onclick=()=>dialog.close();
  $('install-browse').onclick=()=>{dialog.close();$('apk-file').click();};
  return {open(){
    library=null;$('install-search').value='';$('install-projects').replaceChildren();$('install-saved').replaceChildren();
    $('install-target').textContent=`Install on ${device()}`;
    dialog.showModal();void load();
  }};
}
