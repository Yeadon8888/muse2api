import http from 'node:http';
import net from 'node:net';
import { domainToASCII } from 'node:url';

const failure = code => Object.assign(new Error(code), {code});
export function parseAccountSocksConfig(input) {
  if (!input || typeof input !== 'object') throw failure('INVALID_SOCKS_CONFIG');
  const {host, port, username, password} = input;
  if (typeof host !== 'string' || !host || host !== host.trim() || /[\s/@?#]/.test(host)
      || !Number.isInteger(port) || port < 1 || port > 65535
      || [username,password].some(v=>typeof v !== 'string' || Buffer.byteLength(v)<1 || Buffer.byteLength(v)>255)) throw failure('INVALID_SOCKS_CONFIG');
  const timeoutMs = input.timeoutMs ?? 15000;
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 120000) throw failure('INVALID_SOCKS_CONFIG');
  const gatewayHost = input.gatewayHost ?? '';
  const gatewayPort = input.gatewayPort ?? 0;
  if ((gatewayHost || gatewayPort) && (typeof gatewayHost !== 'string' || !gatewayHost
      || !Number.isInteger(gatewayPort) || gatewayPort < 1 || gatewayPort > 65535)) throw failure('INVALID_SOCKS_CONFIG');
  return {host,port,username,password,timeoutMs,gatewayHost,gatewayPort};
}

// Pull only the bytes owned by the handshake; application bytes remain buffered.
function readBytes(socket, size) {
  return new Promise((resolve,reject)=>{
    const cleanup=()=>{socket.off('readable',read);socket.off('error',error);socket.off('close',closed);socket.off('end',closed);};
    const error=()=>{cleanup();reject(failure('SOCKS_CONNECTION_FAILED'));};
    const closed=()=>{cleanup();reject(failure('SOCKS_CONNECTION_CLOSED'));};
    const read=()=>{const bytes=socket.read(size);if(bytes){cleanup();resolve(bytes);}else if(socket.destroyed||socket.readableEnded)closed();};
    socket.on('readable',read);socket.once('error',error);socket.once('close',closed);socket.once('end',closed);read();
  });
}

async function readConnectResponse(socket) {
  const bytes=[];
  while(bytes.length<16384){
    const byte=await readBytes(socket,1);bytes.push(byte[0]);
    const n=bytes.length;
    if(n>=4&&bytes[n-4]===13&&bytes[n-3]===10&&bytes[n-2]===13&&bytes[n-1]===10){
      const status=Buffer.from(bytes).toString('latin1').split('\r\n',1)[0].split(' ');
      if(status.length<2||status[1]!=='200')throw failure('SYSTEM_PROXY_CONNECT_FAILED');
      return;
    }
  }
  throw failure('SYSTEM_PROXY_CONNECT_INVALID');
}

function destination(host,port) {
  const ascii=domainToASCII(host);
  if(!ascii || Buffer.byteLength(ascii)>255 || /[\s\x00/]/.test(ascii) || !Number.isInteger(port)||port<1||port>65535)throw failure('INVALID_PROXY_DESTINATION');
  // Domain addressing intentionally delegates DNS resolution to the SOCKS server.
  const bytes=Buffer.from(ascii);return Buffer.concat([Buffer.from([5,1,0,3,bytes.length]),bytes,Buffer.from([port>>8,port&255])]);
}

export async function startAccountSocksProxy(input) {
  const config=parseAccountSocksConfig(input), sockets=new Set();
  let closing=false, closePromise;
  function track(socket){sockets.add(socket);socket.once('close',()=>sockets.delete(socket));socket.on('error',()=>{});return socket;}
  async function connect(host,port){
    const request=destination(host,port);
    if(closing)throw failure('PROXY_CLOSED');
    const socket=track(net.createConnection({host:config.gatewayHost||config.host,port:config.gatewayPort||config.port}));
    const timer=setTimeout(()=>socket.destroy(failure('SOCKS_TIMEOUT')),config.timeoutMs);
    try{
      await new Promise((resolve,reject)=>{const done=()=>{socket.off('connect',ok);socket.off('error',bad);socket.off('close',bad);};const ok=()=>{done();resolve();};const bad=()=>{done();reject(failure('SOCKS_CONNECTION_FAILED'));};socket.once('connect',ok);socket.once('error',bad);socket.once('close',bad);});
      if(config.gatewayHost){
        const authority=`${config.host}:${config.port}`;
        socket.write(`CONNECT ${authority} HTTP/1.1\r\nHost: ${authority}\r\nProxy-Connection: Keep-Alive\r\n\r\n`);
        await readConnectResponse(socket);
      }
      socket.write(Buffer.from([5,1,2]));
      const greeting=await readBytes(socket,2);
      if(greeting[0]!==5||greeting[1]!==2)throw failure('SOCKS_AUTH_REQUIRED');
      const user=Buffer.from(config.username),pass=Buffer.from(config.password);
      socket.write(Buffer.concat([Buffer.from([1,user.length]),user,Buffer.from([pass.length]),pass]));
      const auth=await readBytes(socket,2);
      if(auth[0]!==1||auth[1]!==0)throw failure('SOCKS_AUTH_FAILED');
      socket.write(request);
      const reply=await readBytes(socket,4);
      if(reply[0]!==5||reply[1]!==0||reply[2]!==0)throw failure('SOCKS_CONNECT_FAILED');
      if(reply[3]===1)await readBytes(socket,6);
      else if(reply[3]===4)await readBytes(socket,18);
      else if(reply[3]===3){const length=await readBytes(socket,1);if(!length[0])throw failure('SOCKS_INVALID_REPLY');await readBytes(socket,length[0]+2);}
      else throw failure('SOCKS_INVALID_REPLY');
      if(closing)throw failure('PROXY_CLOSED');
      return socket;
    }catch(error){socket.destroy();throw failure(error.code?.startsWith('SOCKS_')?error.code:'SOCKS_CONNECTION_FAILED');}
    finally{clearTimeout(timer);}
  }
  const agent=new http.Agent({keepAlive:false});
  agent.createConnection=(options,callback)=>{connect(options.hostname||options.host,Number(options.port)).then(s=>callback(null,s),()=>callback(failure('UPSTREAM_PROXY_FAILED')));};
  const server=http.createServer({maxHeaderSize:16384,headersTimeout:15000,requestTimeout:120000},(req,res)=>{
    let target;
    try{target=new URL(req.url);if(target.protocol!=='http:'||target.username||target.password)throw Error();destination(target.hostname,Number(target.port||80));}
    catch{res.writeHead(400);res.end('INVALID_PROXY_REQUEST');return;}
    const headers={...req.headers,host:target.host};
    for(const key of String(headers.connection||'').split(',').map(s=>s.trim().toLowerCase()))if(key)delete headers[key];
    for(const key of ['proxy-authorization','proxy-connection','connection','keep-alive','upgrade'])delete headers[key];
    const upstream=http.request(target,{method:req.method,headers,agent},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);response.on('error',()=>res.destroy());});
    upstream.on('error',()=>{if(!res.headersSent){res.writeHead(502);res.end('UPSTREAM_PROXY_FAILED');}else res.destroy();});
    req.on('aborted',()=>upstream.destroy());res.on('close',()=>upstream.destroy());req.pipe(upstream);
  });
  server.on('connection',track);
  server.on('clientError',(_error,socket)=>socket.destroy());
  server.on('upgrade',(_req,socket)=>socket.end('HTTP/1.1 501 Not Implemented\r\nConnection: close\r\n\r\n'));
  server.on('connect',async(req,client,head)=>{
    let target;
    try{if(!/^[^/?#@]+:\d+$/.test(req.url))throw Error();target=new URL('http://'+req.url);destination(target.hostname,Number(target.port||80));}
    catch{client.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n');return;}
    client.pause();
    try{
      const upstream=await connect(target.hostname,Number(target.port||80));
      if(client.destroyed){upstream.destroy();return;}
      client.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      client.on('close',()=>upstream.destroy());upstream.on('close',()=>client.destroy());
      if(head.length)upstream.write(head);client.pipe(upstream);upstream.pipe(client);client.resume();
    }catch{if(!client.destroyed)client.end('HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n');}
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',()=>{server.off('error',reject);resolve();});});
  return {url:`http://127.0.0.1:${server.address().port}`,close(){
    if(closePromise)return closePromise;
    closing=true;closePromise=new Promise(resolve=>{server.close(resolve);agent.destroy();for(const socket of sockets)socket.destroy();});return closePromise;
  }};
}
