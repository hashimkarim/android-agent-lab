// Cursor feedback is drawn locally, outside Android capture and video decoding.
export function createCursors(canvas, screen, mode, activity, ownActor, dimensions) {
  const ctx = canvas.getContext('2d');
  const cursors = new Map();
  let latest, animation = 0, timer = 0, width = 0, height = 0;
  const lifetime = 8000;
  const names = {codex:'Codex',claude:'Claude',t3:'T3',human:'Human'};
  const actions = {tap:'Tap',swipe:'Drag',pointer:'Pointer',scroll:'Scroll',typing:'Typing',key:'Key input'};
  const visible = actor => mode.value === 'all' || !actor.startsWith('human:');
  function label(actor) {
    if (actor === ownActor && actor.startsWith('human:')) return 'You';
    const [client, ...rest] = actor.split(':');
    const name = names[client.toLowerCase()] || client;
    return client === 'human' ? 'Human' : name + (rest.length ? ' · ' + rest.join(':').slice(0,22) : '');
  }
  function color(actor) {
    if (actor.startsWith('human:')) return '#68e0cc';
    let hash=2166136261;
    for (const c of actor) hash=Math.imul(hash^c.charCodeAt(0),16777619)>>>0;
    return `hsl(${hash%360} 78% 76%)`;
  }
  function showActivity(text) {if (activity.textContent!==text) activity.textContent=text;}
  function wake() {clearTimeout(timer);timer=0;if (!animation) animation = requestAnimationFrame(draw);}
  const observer = new ResizeObserver(() => {
    const box = screen.getBoundingClientRect(), ratio = devicePixelRatio || 1;
    width = box.width;height = box.height;
    canvas.style.left=screen.offsetLeft+'px';canvas.style.top=screen.offsetTop+'px';
    canvas.style.width=width+'px';canvas.style.height=height+'px';
    canvas.width = Math.round(width * ratio);canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio,0,0,ratio,0,0);wake();
  });
  observer.observe(screen);
  function draw(now) {
    animation = 0;ctx.clearRect(0,0,width,height);
    const rendered = [], labels = [];
    let nextWake = Infinity;
    const size = dimensions();
    for (const [actor,c] of cursors) {
      const age = now - c.updated;
      if (!c.persistent && age >= lifetime) {cursors.delete(actor);continue;}
      if (!visible(actor)) continue;
      if (!size || !c.points) continue;
      const progress = c.kind === 'swipe' ? (c.phase==='complete' ? 1 : Math.min(1,Math.max(0,(now-c.started)/Math.max(1,c.duration)))) : 0;
      const x = (c.points[0] + (c.kind==='swipe' ? (c.points[2]-c.points[0])*progress : 0))/size.width*width;
      const y = (c.points[1] + (c.kind==='swipe' ? (c.points[3]-c.points[1])*progress : 0))/size.height*height;
      const tint = c.ok === false ? '#ff828c' : color(actor);
      ctx.save();ctx.globalAlpha = c.persistent ? 1 : Math.min(1,(lifetime-age)/1200);
      if (actor.startsWith('human:')) {
        // A small touch-style circle, without a human arrow, label, or swipe trail.
        ctx.beginPath();ctx.arc(x,y,c.pressed ? 10 : 7,0,Math.PI*2);
        ctx.fillStyle = c.pressed ? '#c6fff1aa' : '#ffffff38';ctx.fill();
        ctx.strokeStyle='#07131ba8';ctx.lineWidth=3;ctx.stroke();
        ctx.strokeStyle='#f1fffbdc';ctx.lineWidth=1.3;ctx.stroke();ctx.restore();
        rendered.push({actor,kind:c.kind,x,y,shape:'circle',pressed:Boolean(c.pressed)});
        if (!c.persistent) nextWake=Math.min(nextWake,Math.max(1,lifetime-age));
        continue;
      }
      if (c.kind === 'swipe') {
        ctx.strokeStyle=tint;ctx.lineWidth=2;ctx.setLineDash([4,5]);ctx.globalAlpha*=.5;
        ctx.beginPath();ctx.moveTo(c.points[0]/size.width*width,c.points[1]/size.height*height);
        ctx.lineTo(c.points[2]/size.width*width,c.points[3]/size.height*height);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha*=2;
      }
      const pulseAge = now - c.started;
      if (!c.persistent) nextWake=Math.min(nextWake,Math.max(0,lifetime-1200-age));
      if (!c.persistent && (pulseAge<900 || (c.kind==='swipe' && progress<1))) nextWake=0;
      if (!c.persistent && pulseAge < 900) {
        ctx.strokeStyle=tint;ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,8+18*Math.max(0,pulseAge)/900,0,Math.PI*2);ctx.stroke();
      }
      ctx.translate(x,y);ctx.fillStyle=tint;ctx.strokeStyle='#111820';ctx.lineWidth=1.5;
      ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(2,24);ctx.lineTo(8,18);ctx.lineTo(13,29);ctx.lineTo(18,26);ctx.lineTo(12,15);ctx.lineTo(21,14);ctx.closePath();ctx.fill();ctx.stroke();
      ctx.translate(-x,-y);
      const text = label(actor)+(c.ok===false ? ' · failed' : '');
      ctx.font='600 12px system-ui';
      const labelWidth=Math.min(width-8,ctx.measureText(text).width+16);
      const labelX=Math.max(4,Math.min(width-labelWidth-4,x+18));
      let labelY=y+30>height-28 ? Math.max(4,y-30) : y+30;
      for (let attempt=0;attempt<labels.length+1;attempt++) {
        const overlap=labels.find(r=>labelX<r.x+r.width && labelX+labelWidth>r.x && labelY<r.y+28 && labelY+28>r.y);
        if (!overlap) break;
        labelY=overlap.y+28<height-28 ? overlap.y+28 : Math.max(4,overlap.y-28);
      }
      labels.push({x:labelX,y:labelY,width:labelWidth});
      ctx.fillStyle=tint;ctx.beginPath();ctx.roundRect(labelX,labelY,labelWidth,24,5);ctx.fill();
      ctx.fillStyle='#111820';ctx.fillText(text,labelX+8,labelY+16,labelWidth-16);ctx.restore();
      rendered.push({actor,kind:c.kind,x,y,ok:c.ok,shape:'arrow'});
    }
    canvas.dataset.markers=JSON.stringify(rendered);
    if (latest && visible(latest.actor) && now-latest.updated < lifetime) {
      showActivity(`${label(latest.actor)} · ${latest.key || actions[latest.kind]}${latest.ok===false ? ' failed' : ''}`);
      nextWake=Math.min(nextWake,lifetime-(now-latest.updated));
    } else {latest=null;showActivity('Agent cursors ready');}
    if (nextWake===0) wake();
    else if (Number.isFinite(nextWake)) timer=setTimeout(wake,Math.max(1,nextWake));
  }
  mode.onchange = () => {localStorage.setItem('adb-cursor-mode',mode.value);screen.style.cursor=mode.value==='all' ? 'none' : 'default';wake();};
  mode.value=localStorage.getItem('adb-cursor-mode')==='agents' ? 'agents' : 'all';
  mode.onchange();
  return {
    receive(message, local=false) {
      for (const event of message.events || []) {
        if (typeof event.actor !== 'string' || !actions[event.kind]) continue;
        // Delayed broker feedback must never move a locally drawn live pointer backwards.
        if (event.actor===ownActor && !local && (event.persistent || cursors.get(ownActor)?.local)) continue;
        if (event.phase==='leave') {cursors.delete(event.actor);if (latest?.actor===event.actor) latest=null;continue;}
        const updated=performance.now()-Math.max(0,message.now-event.at*1000);
        if (performance.now()-updated >= lifetime) continue;
        const previous=cursors.get(event.actor);
        const c={...event,local,updated,started:previous?.id===event.id ? previous.started : updated};
        if (event.points) {
          if (cursors.size>=12 && !cursors.has(event.actor)) cursors.delete(cursors.keys().next().value);
          cursors.set(event.actor,c);
        }
        latest=c;
      }
      wake();
    },
    clear() {cancelAnimationFrame(animation);animation=0;clearTimeout(timer);timer=0;cursors.clear();latest=null;canvas.dataset.markers='[]';activity.textContent='Agent cursors ready';ctx.clearRect(0,0,width,height);},
  };
}
