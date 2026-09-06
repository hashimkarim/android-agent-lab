// Bound encoded-frame work without discarding a delta frame's dependencies.
// After congestion we resume at an independently decodable keyframe.
export class VideoPacketQueue {
  constructor(write, onError, limit=8) {
    this.write=write;this.onError=onError;this.limit=limit;
    this.queue=[];this.running=false;this.waiting=false;this.dropped=0;this.closed=false;
  }
  push(packet) {
    if (this.closed) return;
    if (packet.type==='configuration') {this.queue=[];this.waiting=true;this.queue.push(packet);}
    else {
      if (this.queue.length>=this.limit) {
        this.dropped+=this.queue.filter(p=>p.type==='data').length;
        this.queue=this.queue.filter(p=>p.type==='configuration');this.waiting=true;
      }
      if (this.waiting && !packet.keyframe) {this.dropped++;return;}
      if (packet.keyframe) this.waiting=false;
      this.queue.push(packet);
    }
    void this.drain();
  }
  async drain() {
    if (this.running) return;
    this.running=true;
    try {while (this.queue.length && !this.closed) await this.write(this.queue.shift());}
    catch(error) {this.close();this.onError(error);}
    finally {this.running=false;}
  }
  close() {this.closed=true;this.queue=[];}
}

// Draw VideoFrame directly, avoiding asynchronous ImageBitmap allocation for
// every frame. Desynchronized canvas requests the browser's low-latency path.
export class DirectCanvasRenderer {
  constructor(canvas) {this.canvas=canvas;this.context=canvas.getContext('2d',{alpha:false,desynchronized:true});if(!this.context)throw Error('Canvas rendering is unavailable.');}
  setSize(width,height) {if(this.canvas.width!==width)this.canvas.width=width;if(this.canvas.height!==height)this.canvas.height=height;}
  draw(frame) {this.context.drawImage(frame,0,0);}
}
