const bodyless = method => method === 'GET' || method === 'HEAD';
const mediaPath = /^\/v1\/media\/([^/]+)$/;
const uploadPath = /^\/_internal\/media\/([^/]+)$/;

function mediaName(match) {
  if (!match) return null;
  try {
    const name = decodeURIComponent(match[1]);
    return /^[A-Za-z0-9._-]+$/.test(name) && !name.includes('..') ? name : null;
  } catch {
    return null;
  }
}

function r2Headers(object) {
  const headers = new Headers();
  object.writeHttpMetadata?.(headers);
  if (!headers.has('content-type')) headers.set('content-type', 'application/octet-stream');
  if (object.httpEtag) headers.set('etag', object.httpEtag);
  headers.set('cache-control', 'public, max-age=31536000, immutable');
  headers.set('content-length', String(object.size));
  headers.set('x-muse2api-storage', 'r2');
  headers.set('accept-ranges', 'bytes');
  return headers;
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);

    if (incoming.pathname === '/_internal/media') {
      if (!env.MEDIA_UPLOAD_TOKEN || request.headers.get('x-muse-media-token') !== env.MEDIA_UPLOAD_TOKEN) {
        return new Response('unauthorized', {status: 401});
      }
      if (request.method !== 'GET') {
        return new Response('method not allowed', {status: 405, headers: {allow: 'GET'}});
      }
      const listed = await env.MEDIA_BUCKET.list({limit: 1000, cursor: incoming.searchParams.get('cursor') || undefined, include: ['httpMetadata', 'customMetadata']});
      return Response.json({
        objects: listed.objects.map(object => ({
          name: object.key,
          bytes: object.size,
          uploaded: object.uploaded?.toISOString?.() || object.uploaded || null,
          content_type: object.httpMetadata?.contentType || 'application/octet-stream'
        })),
        truncated: listed.truncated,
        cursor: listed.truncated ? listed.cursor : null
      });
    }

    const internalName = mediaName(incoming.pathname.match(uploadPath));
    if (incoming.pathname.startsWith('/_internal/media/')) {
      if (!internalName) return new Response('invalid media name', {status: 400});
      if (!env.MEDIA_UPLOAD_TOKEN || request.headers.get('x-muse-media-token') !== env.MEDIA_UPLOAD_TOKEN) {
        return new Response('unauthorized', {status: 401});
      }
      if (request.method === 'PUT') {
        const declaredSize = Number(request.headers.get('content-length') || 0);
        if (declaredSize > 100 * 1024 * 1024) return new Response('media too large', {status: 413});
        await env.MEDIA_BUCKET.put(internalName, request.body, {
          httpMetadata: {contentType: request.headers.get('content-type') || 'application/octet-stream'},
          customMetadata: {source: 'muse2api-railway'}
        });
        return Response.json({ok: true, url: `${incoming.origin}/v1/media/${encodeURIComponent(internalName)}`});
      }
      if (request.method === 'DELETE') {
        await env.MEDIA_BUCKET.delete(internalName);
        return Response.json({ok: true});
      }
      return new Response('method not allowed', {status: 405, headers: {allow: 'PUT, DELETE'}});
    }

    const publicName = mediaName(incoming.pathname.match(mediaPath));
    if (publicName && env.MEDIA_BUCKET && (request.method === 'GET' || request.method === 'HEAD')) {
      try {
        const metadata = await env.MEDIA_BUCKET.head(publicName);
        if (metadata) {
          const headers = r2Headers(metadata);
          if (request.method === 'HEAD') return new Response(null, {headers});
          let range;
          const raw = request.headers.get('range');
          const ifRange = request.headers.get('if-range');
          if (raw && (!ifRange || ifRange === metadata.httpEtag)) {
            const match = /^bytes=(\d*)-(\d*)$/.exec(raw);
            if (match && (match[1] || match[2])) {
              const size = metadata.size;
              const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
              const end = match[1] && match[2] ? Math.min(size - 1, Number(match[2])) : size - 1;
              if (start >= size || start > end || !Number.isSafeInteger(start) || !Number.isSafeInteger(end)) {
                return new Response(null, {status: 416, headers: {'content-range': `bytes */${size}`}});
              }
              range = {offset: start, length: end - start + 1};
              headers.set('content-range', `bytes ${start}-${end}/${size}`);
              headers.set('content-length', String(range.length));
            }
          }
          const object = await env.MEDIA_BUCKET.get(publicName, range ? {range} : undefined);
          if (object) return new Response(object.body, {status: range ? 206 : 200, headers});
        }
      } catch {
        // R2 临时不可用时仍允许从 Railway 本地副本读取。
      }
    }

    const upstreamOrigin = new URL(env.UPSTREAM_ORIGIN);
    const upstream = new URL(incoming.pathname + incoming.search, upstreamOrigin);
    const headers = new Headers(request.headers);
    headers.delete('x-muse-media-fallback');
    if (publicName) headers.set('x-muse-media-fallback', '1');
    headers.set('x-forwarded-host', incoming.host);
    headers.set('x-forwarded-proto', incoming.protocol.slice(0, -1));
    headers.set('x-forwarded-for', request.headers.get('cf-connecting-ip') || '');
    headers.delete('cf-connecting-ip');
    headers.delete('cf-ray');
    headers.delete('cf-visitor');

    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body: bodyless(request.method) ? undefined : request.body,
      redirect: 'manual'
    });
    const outputHeaders = new Headers(response.headers);
    const location = outputHeaders.get('location');
    if (location?.startsWith(upstreamOrigin.origin)) {
      outputHeaders.set('location', incoming.origin + location.slice(upstreamOrigin.origin.length));
    }
    outputHeaders.set('x-muse2api-relay', 'mature-v1');
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: outputHeaders
    });
  }
};
