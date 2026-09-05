import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';

export class LockBroker {
  constructor(config, script, onFailure) {
    this.pending = new Map(); this.next = 0; this.closed = false;
    this.child = spawn(config.python, [script], {env:process.env, stdio:['pipe','pipe','pipe']});
    this.child.stdin.on('error', () => {});
    let error = '';
    this.child.stderr.on('data', chunk => { error = (error + chunk).slice(-4000); });
    createInterface({input:this.child.stdout}).on('line', line => {
      try {
        const result = JSON.parse(line), pending = this.pending.get(result.id);
        if (!pending) return;
        this.pending.delete(result.id); clearTimeout(pending.timer);
        result.ok ? pending.resolve() : pending.reject(new Error(result.error));
      } catch { this.child.kill(); }
    });
    const failed = () => {
      for (const p of this.pending.values()) {clearTimeout(p.timer);p.reject(new Error(error || 'Device lock service stopped'));}
      this.pending.clear();
      if (!this.closed) { this.closed = true; onFailure(); }
    };
    this.child.on('error', failed); this.child.on('close', failed);
  }
  request(action, event, ok = true) {
    if (this.closed) return Promise.reject(new Error('Device lock service stopped'));
    const id = ++this.next;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.child.kill(); }, 5000);
      this.pending.set(id, {resolve,reject,timer});
      this.child.stdin.write(JSON.stringify({id, action, event, ok})+'\n');
    });
  }
  acquire(event) { return this.request('acquire', event); }
  release(event, ok) { return this.request('release', event, ok); }
  close() { this.closed = true; this.child.stdin.end(); }
}
