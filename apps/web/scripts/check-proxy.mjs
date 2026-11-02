// Isolated proxy contract checks: no database, credentials or model calls.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createServer, request } from 'node:http'
import { resolve } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'

const upstream = createServer((req, res) => {
  if (req.url.endsWith('/slow')) {
    setTimeout(() => {
      res.end(JSON.stringify({ complete: true }))
    }, 31_000)
    return
  }
  let bytes = 0
  const hash = createHash('sha256')
  req.on('data', (chunk) => {
    bytes += chunk.length
    hash.update(chunk)
  })
  req.on('end', () =>
    res.end(
      JSON.stringify({
        bytes,
        digest: hash.digest('hex'),
        authorization: req.headers.authorization,
        contentType: req.headers['content-type'],
      })
    )
  )
})
await new Promise((ready) => upstream.listen(0, '127.0.0.1', ready))
const origin = 'http://127.0.0.1:' + upstream.address().port
const base = 'http://127.0.0.1:3002'
const child = spawn(
  process.execPath,
  [
    'node_modules/next/dist/bin/next',
    'dev',
    '--hostname',
    '127.0.0.1',
    '--port',
    '3002',
  ],
  {
    cwd: resolve(import.meta.dirname, '..'),
    detached: true,
    env: { ...process.env, API_ORIGIN: origin, NEXT_TELEMETRY_DISABLED: '1' },
    stdio: 'ignore',
  }
)
try {
  let ready = false
  for (let attempt = 0; attempt < 120; attempt++) {
    if (child.exitCode !== null)
      throw new Error('Proxy test server exited: ' + child.exitCode)
    try {
      const response = await fetch(base + '/api/proxy-check/ready')
      if (response.ok) {
        ready = true
        break
      }
    } catch {}
    await delay(250)
  }
  assert.ok(ready, 'Isolated Next proxy must start')
  const boundary = 'tender-migration-proxy-check'
  const payload = Buffer.concat([
    Buffer.from(
      '--' +
        boundary +
        '\r\nContent-Disposition: form-data; name="file"; filename="fictional.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
    ),
    Buffer.alloc(11 * 1024 * 1024, 97),
    Buffer.from('\r\n--' + boundary + '--\r\n'),
  ])
  const upload = new Promise((resolveUpload, reject) => {
    const req = request(
      base + '/api/proxy-check/upload',
      {
        method: 'POST',
        headers: {
          authorization: 'Bearer synthetic-proxy-token',
          'content-type': 'multipart/form-data; boundary=' + boundary,
        },
      },
      (res) => {
        let body = ''
        res.on('data', (chunk) => {
          body += chunk
        })
        res.on('end', () => {
          try {
            assert.equal(res.statusCode, 200)
            const result = JSON.parse(body)
            assert.equal(
              result.bytes,
              payload.length,
              'Multipart bytes must reach the API without truncation'
            )
            assert.equal(
              result.digest,
              createHash('sha256').update(payload).digest('hex')
            )
            assert.equal(result.authorization, 'Bearer synthetic-proxy-token')
            assert.equal(
              result.contentType,
              'multipart/form-data; boundary=' + boundary
            )
            resolveUpload()
          } catch (error) {
            reject(error)
          }
        })
      }
    )
    req.on('error', reject)
    req.setTimeout(45_000, () =>
      req.destroy(new Error('Upload proxy timed out'))
    )
    req.write(payload)
    req.end()
  })
  const slow = (async () => {
    const response = await fetch(base + '/api/proxy-check/slow', {
      signal: AbortSignal.timeout(45_000),
    })
    assert.equal(
      response.status,
      200,
      'Assistant responses longer than 30 seconds must reach the browser'
    )
    assert.deepEqual(await response.json(), { complete: true })
  })()
  const results = await Promise.allSettled([upload, slow])
  for (const [i, result] of results.entries()) {
    if (result.status === 'rejected')
      console.error(
        ['Multipart fidelity', 'Slow response'][i] +
          ': ' +
          result.reason.message
      )
  }
  assert.ok(
    results.every((result) => result.status === 'fulfilled'),
    'Proxy contract checks failed'
  )
  console.log(
    'Proxy checks passed: 11 MiB multipart bytes/headers and a 31-second response.'
  )
} finally {
  if (child.exitCode === null) process.kill(-child.pid, 'SIGTERM')
  upstream.closeAllConnections()
  await new Promise((closed) => upstream.close(closed))
}
