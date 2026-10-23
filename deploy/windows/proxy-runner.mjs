import {startAccountSocksProxy} from './account-socks-proxy.mjs';

const encoded=process.env.MUSE2API_SOCKS_CONFIG;
if(!encoded)throw new Error('MUSE2API_SOCKS_CONFIG is required');
const config=JSON.parse(Buffer.from(encoded,'base64url').toString('utf8'));
delete process.env.MUSE2API_SOCKS_CONFIG;
const proxy=await startAccountSocksProxy(config);
process.stdout.write(`${proxy.url}\n`);
const stop=async()=>{await proxy.close();process.exit(0);};
process.once('SIGINT',stop);
process.once('SIGTERM',stop);
await new Promise(()=>{});
