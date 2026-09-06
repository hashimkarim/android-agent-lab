const {test}=require('node:test');
const assert=require('node:assert/strict');
const QRCode=require('qrcode');
const {createWorkspace}=require('../app/workspace.cjs');

test('QR pairing matches only its advertised service, expires, and respects cancellation',async()=>{
  const encode=QRCode.toDataURL, calls=[];let payload, blockDiscovery;
  QRCode.toDataURL=async(value,options)=>{payload=value;return encode(value,options);};
  const workspace=createWorkspace({sessions:new Map(),rpc:async data=>{
    calls.push(data);
    if(data.action==='discover'){
      if(blockDiscovery)await new Promise(r=>{blockDiscovery=r;});
      return {services:[{kind:'pairing',name:'studio-someone-else',address:'192.168.1.8:40000'},
        {kind:'pairing',name:payload.match(/;S:([^;]+);/)[1],address:'192.168.1.9:41000'}]};
    }
    assert.equal(data.action,'pair');return{message:'Paired'};
  }});
  try{
    const first=await workspace.actions.qrStart();
    assert.match(first.image,/^data:image\/png;base64,/);
    assert.match(payload,/^WIFI:T:ADB;S:studio-[a-f0-9]{10};P:[a-f0-9]{32};;$/);
    const expectedSecret=payload.match(/;P:([^;]+);/)[1];
    assert.equal((await workspace.actions.qrPoll({id:first.id})).paired,true);
    assert.deepEqual(calls.find(c=>c.action==='pair'),{action:'pair',address:'192.168.1.9:41000',code:expectedSecret});
    assert.equal((await workspace.actions.qrPoll({id:first.id})).expired,true);
    const next=await workspace.actions.qrStart();blockDiscovery=true;
    const waiting=workspace.actions.qrPoll({id:next.id});await Promise.resolve();
    workspace.actions.qrCancel();blockDiscovery();
    assert.equal((await waiting).expired,true);
    assert.equal(calls.filter(c=>c.action==='pair').length,1);
  }finally{QRCode.toDataURL=encode;await workspace.shutdown();}
});

test('pairing connects the matching device identity and skips a stale advertised port',async()=>{
  const calls=[];
  const workspace=createWorkspace({sessions:new Map(),rpc:async data=>{
    calls.push(data);
    if(data.action==='pair')return {guid:'adb-watch'};
    if(data.action==='discover')return {services:[
      {name:'adb-other',kind:'connect',address:'192.168.1.159:40001'},
      {name:'adb-watch',kind:'connect',address:'192.168.1.159:39667'},
      {name:'adb-watch (2)',kind:'connect',address:'192.168.1.159:43443'},
      {name:'adb-watch',kind:'connect',address:'192.168.1.9:43443'},
    ]};
    if(data.address.endsWith(':39667'))throw Error('Connection refused');
    assert.equal(data.address,'192.168.1.159:43443');return {message:'connected'};
  }});
  try {
    const result=await workspace.actions.pair({address:'192.168.1.159:41111',code:'123456'});
    assert.equal(result.connected,true);assert.equal(result.address,'192.168.1.159:43443');
    assert.deepEqual(calls.filter(c=>c.action==='connect').map(c=>c.address),['192.168.1.159:39667','192.168.1.159:43443']);
  }finally{await workspace.shutdown();}
});

test('successful pairing remains successful if discovery is missing or identity is ambiguous',async()=>{
  for(const services of [[],[{name:'one',kind:'connect',address:'192.168.1.2:40000'},{name:'two',kind:'connect',address:'192.168.1.2:40001'}]]) {
    const workspace=createWorkspace({sessions:new Map(),rpc:async data=>{
      if(data.action==='pair')return {message:'Paired'};
      assert.equal(data.action,'discover');return {services,available:services.length>0};
    }});
    try{
      const result=await workspace.actions.pair({address:'192.168.1.2:41000',code:'123456'});
      assert.equal(result.paired,true);assert.equal(result.connected,false);
      assert.match(result.message,/connection port/);
    }finally{await workspace.shutdown();}
  }
});

test('QR discovery errors offer manual pairing without repeated failures',async()=>{
  const workspace=createWorkspace({sessions:new Map(),rpc:async data=>{
    assert.equal(data.action,'discover');return {services:[],available:false,message:'Use a pairing code and manual IP/port.'};
  }});
  try{
    const qr=await workspace.actions.qrStart();
    const result=await workspace.actions.qrPoll({id:qr.id});
    assert.equal(result.unavailable,true);assert.match(result.message,/pairing code/);
  }finally{await workspace.shutdown();}
});
