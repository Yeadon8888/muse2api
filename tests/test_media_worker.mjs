import assert from 'node:assert/strict';
import worker from '../deploy/media-worker/index.mjs';
const data = new TextEncoder().encode('0123456789');
const metadata = {size: 10, httpEtag: '"fixture"', writeHttpMetadata(h) {h.set('content-type', 'video/mp4')}};
const env = {UPSTREAM_ORIGIN: 'https://origin.invalid', MEDIA_BUCKET: {
  async head() {return metadata},
  async get(name, options) {const r=options?.range; return {...metadata, body:r ? data.slice(r.offset,r.offset+r.length):data}}
}};
for (const [range, status, body] of [[null,200,'0123456789'],['bytes=2-5',206,'2345'],['bytes=-3',206,'789'],['bytes=8-',206,'89'],['bytes=100-',416,'']]) {
  const response=await worker.fetch(new Request('https://relay.invalid/v1/media/fixture.mp4',{headers:range?{range}:{}}),env);
  assert.equal(response.status,status); assert.equal(await response.text(),body);
}
const head=await worker.fetch(new Request('https://relay.invalid/v1/media/fixture.mp4',{method:'HEAD'}),env);
assert.equal(head.headers.get('content-length'),'10'); assert.equal(await head.text(),'');
globalThis.fetch=async(url, options)=>{assert.equal(options.headers.get('x-muse-media-fallback'),'1');return new Response('local')};
env.MEDIA_BUCKET.head=async()=>null;
assert.equal(await (await worker.fetch(new Request('https://relay.invalid/v1/media/missing.mp4'),env)).text(),'local');
env.MEDIA_BUCKET.head=async()=>{throw new Error('unavailable')};
assert.equal(await (await worker.fetch(new Request('https://relay.invalid/v1/media/missing.mp4'),env)).text(),'local');
console.log('media worker: passed');
