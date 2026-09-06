import {request} from 'node:http';

export function desktopLibrary({serial,token}, env=process.env) {
  const available=Boolean(env.ADB_LAB_LIBRARY_SOCKET && env.ADB_LAB_LIBRARY_KEY);
  return {available, call(data) {
    if(!available) return data.action==='catalog'?Promise.resolve({available:false,projects:[],apks:[]}):Promise.reject(Error('Open this device from Android Agent Lab to use saved projects.'));
    return new Promise((resolve,reject)=>{
      const req=request({socketPath:env.ADB_LAB_LIBRARY_SOCKET,path:'/',method:'POST',headers:{'Content-Type':'application/json','X-Lab-Library-Key':env.ADB_LAB_LIBRARY_KEY}},res=>{
        let output='';
        res.on('data',chunk=>{output+=chunk;if(output.length>2*1024*1024)req.destroy(Error('Library response too large.'));});
        res.on('end',()=>{try{const value=JSON.parse(output);res.statusCode===200?resolve(value):reject(Error(value.error||'Library request failed.'));}catch(error){reject(error);}});
        res.on('error',reject);
      });
      req.setTimeout(30000,()=>req.destroy(Error('Desktop library request timed out.')));
      req.on('error',reject);
      // Browser-supplied values never choose a different device or claim.
      req.end(JSON.stringify({...data,serial,token}));
    });
  }};
}
