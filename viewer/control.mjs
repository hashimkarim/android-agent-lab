import {randomUUID} from 'node:crypto';
import {AndroidKeyCode} from '@yume-chan/scrcpy';

const keys = {BACK:4, HOME:3, APP_SWITCH:187, ENTER:66, TAB:61, DEL:67,
  DPAD_LEFT:21, DPAD_RIGHT:22, DPAD_UP:19, DPAD_DOWN:20, POWER:26,
  VOLUME_UP:24, VOLUME_DOWN:25, VOLUME_MUTE:164, MENU:82};
const motions = {down:0, up:1, move:2, cancel:3};
const validActor = actor => typeof actor === 'string' && actor.trim() && actor.length <= 80 && !/[\x00-\x1f\x7f]/.test(actor);

export class LiveControl {
  constructor({controller, broker, owns, size, physicalSize, broadcast}) {
    Object.assign(this, {controller,broker,owns,size,physicalSize,broadcast});
    this.active = null; this.tail = Promise.resolve(); this.queued = 0;
    this.presence = new Map(); this.closed = false; this.timer = null;
  }
  actor(data) {
    if (!validActor(data.actor)) throw new Error('Use a nonempty actor label of at most 80 characters.');
    return data.actor.trim();
  }
  point(data) {
    const {width, height} = this.size();
    if (data.width !== width || data.height !== height || !width || !height) throw new Error('Display size changed; wait for the next frame and retry.');
    if (![data.x,data.y].every(Number.isFinite) || data.x < 0 || data.x >= width || data.y < 0 || data.y >= height) throw new Error('Pointer is outside the video frame.');
    return {pointerX:Math.min(width-1,Math.round(data.x)), pointerY:Math.min(height-1,Math.round(data.y)), videoWidth:width, videoHeight:height};
  }
  event(data, id = randomUUID()) {
    const event = {id, actor:this.actor(data), kind:data.kind === 'pointer' || data.kind === 'hover' ? 'pointer' : data.kind === 'text' || data.kind === 'clipboard' ? 'typing' : data.kind === 'scroll' ? 'scroll' : 'key'};
    if (['pointer','hover','scroll'].includes(data.kind)) {
      const p = this.point(data); let {width,height} = this.physicalSize();
      if ((width > height) !== (p.videoWidth > p.videoHeight)) [width,height] = [height,width];
      event.points = [p.pointerX / p.videoWidth * width, p.pointerY / p.videoHeight * height];
    }
    return event;
  }
  publish(event, phase, extra = {}) {
    this.broadcast({type:'activity', now:Date.now(), events:[{...event, at:Date.now()/1000, phase, ...extra}]});
  }
  hover(owner, data) {
    if (this.closed || !this.owns()) throw new Error('Device claim expired or changed.');
    const actor = this.actor(data);
    if (data.phase === 'leave') { this.leave(owner); return; }
    const previous = this.presence.get(owner);
    const event = this.event({...data,actor}, previous?.id);
    event.persistent = true;
    this.presence.set(owner, {...event,pressed:Boolean(this.active?.owner === owner)});
    // Hover is visual presence, not Android input. It never acquires or renews a claim.
    this.publish(event, 'hover', {pressed:Boolean(this.active?.owner === owner)});
  }
  leave(owner) {
    const event = this.presence.get(owner);
    if (event) { this.publish(event, 'leave'); this.presence.delete(owner); }
  }
  submit(owner, data) {
    if (data?.kind === 'hover') { try { this.hover(owner, data); return Promise.resolve(); } catch (e) { return Promise.reject(e); } }
    // Keep down/up/cancel and other actors ordered, but don't replay obsolete
    // positions after a slow socket or lock acquisition. Merge only adjacent
    // pending moves from the same gesture owner.
    if (data?.kind==='pointer' && data.phase==='move' && this.lastQueued?.owner===owner &&
        !this.lastQueued.started && this.lastQueued.data.kind==='pointer' &&
        this.lastQueued.data.phase==='move' && this.lastQueued.data.actor===data.actor) {
      this.lastQueued.data=data;
      return this.lastQueued.result;
    }
    if (this.queued >= 64) return Promise.reject(new Error('Input is congested. Release the pointer and retry.'));
    this.queued++;
    const entry={owner,data,started:false};
    const result = this.tail.then(() => {
      entry.started=true;if(this.lastQueued===entry)this.lastQueued=null;
      return this.handle(owner, entry.data);
    });
    entry.result=result;this.lastQueued=entry;
    this.tail = result.catch(() => {}).finally(() => this.queued--);
    return result;
  }
  async handle(owner, data) {
    if (this.closed || !this.owns()) throw new Error('Device claim expired or changed.');
    if (!this.controller || !this.broker) throw new Error('This viewer is read-only.');
    this.actor(data);
    if (data.kind === 'pointer') return this.pointer(owner, data);
    const event = this.event(data);
    if (this.active) throw new Error('Another gesture is in progress. Release it before using another control.');
    await this.broker.acquire(event);
    let ok = false;
    try {
      if (!this.owns()) throw new Error('Device claim changed.');
      this.publish(event, 'start');
      switch (data.kind) {
        case 'key': {
          const keyCode = keys[data.key] ?? AndroidKeyCode[data.code];
          if (!Number.isInteger(keyCode)) throw new Error('Unsupported key.');
          const metaState = Number.isInteger(data.meta) && data.meta >= 0 && data.meta <= 0x7fffff ? data.meta : 0;
          await this.controller.injectKeyCode({action:0, keyCode, repeat:0, metaState});
          await this.controller.injectKeyCode({action:1, keyCode, repeat:0, metaState});
          break;
        }
        case 'text':
          if (typeof data.text !== 'string' || !data.text.length || data.text.length > 4000) throw new Error('Use 1–4000 characters.');
          await this.controller.injectText(data.text); break;
        case 'clipboard':
          if (typeof data.text !== 'string' || data.text.length > 16000) throw new Error('Clipboard text is too large.');
          await this.controller.setClipboard({sequence:0n, content:data.text, paste:true}); break;
        case 'scroll':
          if (![data.scrollX,data.scrollY].every(n => Number.isFinite(n) && Math.abs(n) <= 1)) throw new Error('Invalid scroll distance.');
          await this.controller.injectScroll({...this.point(data),scrollX:data.scrollX,scrollY:data.scrollY,buttons:0}); break;
        case 'command': {
          const commands = {rotate:'rotateDevice', notifications:'expandNotificationPanel', 'quick-settings':'expandSettingPanel', collapse:'collapseNotificationPanel', 'reset-video':'resetVideo'};
          if (!Object.hasOwn(commands, data.command)) throw new Error('Unknown device control.');
          await this.controller[commands[data.command]](); break;
        }
        default: throw new Error('Unknown input type.');
      }
      ok = true;
    } finally {
      this.publish(event, 'complete', {ok});
      await this.broker.release(event, ok);
    }
  }
  async pointer(owner, data) {
    if (!Object.hasOwn(motions, data.phase)) throw new Error('Invalid pointer phase.');
    const point = this.point(data);
    if (data.phase === 'down') {
      if (this.active) throw new Error('Another pointer is already touching the device.');
      const event = this.event(data);
      await this.broker.acquire(event);
      this.active = {owner, event, point, started:Date.now()};
    } else if (!this.active || this.active.owner !== owner || this.active.event.actor !== data.actor.trim()) {
      throw new Error('This pointer does not own the current gesture.');
    }
    const active = this.active;
    if (Date.now() - active.started > 30000) { await this.cancel(owner); throw new Error('Gesture exceeded 30 seconds.'); }
    active.event = this.event(data, active.event.id); active.point = point;
    const ending = data.phase === 'up' || data.phase === 'cancel';
    try {
      await this.controller.injectTouch({...point,action:motions[data.phase],pointerId:-2n,pressure:ending ? 0 : 1,actionButton:0,buttons:0});
      this.publish(active.event, data.phase, {pressed:!ending, persistent:true});
      this.presence.set(owner, {...active.event,persistent:true,pressed:!ending});
      if (ending) await this.finish(data.phase !== 'cancel');
      else {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => {
          this.tail = this.tail.then(() => this.cancel(owner)).catch(() => {});
        }, 10000);
        this.timer.unref();
      }
    } catch (error) { await this.cancel(owner); throw error; }
  }
  async finish(ok) {
    clearTimeout(this.timer);
    const active = this.active; this.active = null;
    if (active) await this.broker.release(active.event, ok);
  }
  async cancel(owner) {
    if (!this.active || this.active.owner !== owner) return;
    const active = this.active;
    try {
      await this.controller.injectTouch({...active.point, action:3, pointerId:-2n, pressure:0, actionButton:0, buttons:0});
      this.publish(active.event, 'cancel', {pressed:false});
    } finally { await this.finish(false); }
  }
  disconnect(owner) {
    this.leave(owner);
    const result = this.tail.then(async () => {try {await this.cancel(owner);} finally {this.leave(owner);}});
    this.tail = result.catch(() => {});
    return result;
  }
  async close() {
    this.closed = true;
    await this.tail;
    if (this.active) await this.cancel(this.active.owner);
    this.broker?.close();
  }
}
