import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchRead, networkMessage } from '../lib/network.mjs';
import { createServer } from 'node:http';
import { connect } from 'node:net';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

test('transport disconnects retry once; HTTP authentication and quotas do not retry', async () => {
  const original = globalThis.fetch;
  try {
    let calls = 0;
    globalThis.fetch = async () => { if (++calls === 1) throw new TypeError('fetch failed', {cause:{code:'ECONNRESET'}}); return new Response('ok'); };
    assert.equal(await (await fetchRead('https://github.com')).text(), 'ok');
    assert.equal(calls, 2);
    for (const status of [401, 403, 429]) {
      calls = 0;
      globalThis.fetch = async () => { calls++; return new Response('', {status}); };
      assert.equal((await fetchRead('https://github.com')).status, status);
      assert.equal(calls, 1);
    }
    calls = 0;
    globalThis.fetch = async () => { calls++; throw new TypeError('fetch failed', {cause:{code:'CERT_HAS_EXPIRED'}}); };
    await assert.rejects(fetchRead('https://github.com'), /安全连接/);
    assert.equal(calls, 1);
    globalThis.fetch = async () => { throw new TypeError('fetch failed', {cause:{code:'ECONNREFUSED'}}); };
    await assert.rejects(fetchRead('https://github.com'), /代理是否已启动/);
  } finally { globalThis.fetch = original; }
});

test('network errors explain timeout and DNS without exposing URLs or credentials', () => {
  assert.match(networkMessage({name:'TimeoutError'}), /超时/);
  assert.match(networkMessage({cause:{errors:[{code:'ENOTFOUND'}]}}), /DNS/);
});

test('Node child uses the configured proxy while loopback bypasses it', async () => {
  const origin = createServer((_, res) => res.end('fixture-origin'));
  const proxy = createServer((_, res) => res.end('fixture-proxy'));
  const requests = [], sockets = new Set();
  proxy.on('connect', (req, client, head) => {
    requests.push(req.url);
    const upstream = connect(origin.address().port, '127.0.0.1', () => {
      client.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      if (head.length) upstream.write(head);
      client.pipe(upstream); upstream.pipe(client);
    });
    sockets.add(client); sockets.add(upstream);
    client.on('error', () => upstream.destroy()); upstream.on('error', () => client.destroy());
    client.on('close', () => upstream.destroy());
  });
  await new Promise(r => origin.listen(0, '127.0.0.1', r));
  await new Promise(r => proxy.listen(0, '127.0.0.1', r));
  try {
    const env = {...process.env, NODE_USE_ENV_PROXY:'1', HTTP_PROXY:`http://127.0.0.1:${proxy.address().port}`, NO_PROXY:'localhost,127.0.0.1'};
    delete env.http_proxy; delete env.no_proxy;
    const script = `console.log(await (await fetch('http://proxy-fixture.invalid:8123',{signal:AbortSignal.timeout(5000)})).text());console.log(await (await fetch('http://127.0.0.1:${origin.address().port}',{signal:AbortSignal.timeout(5000)})).text());`;
    const {stdout} = await promisify(execFile)(process.execPath, ['-e', script], {env, timeout:10000, windowsHide:true});
    assert.deepEqual(stdout.trim().split(/\r?\n/), ['fixture-origin', 'fixture-origin']);
    assert.deepEqual(requests, ['proxy-fixture.invalid:8123']);
  } finally {
    for (const socket of sockets) socket.destroy();
    origin.closeAllConnections(); proxy.closeAllConnections();
    await Promise.all([new Promise(r => origin.close(r)), new Promise(r => proxy.close(r))]);
  }
});
