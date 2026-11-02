// Real React state/callback regression plus the actual auth/settings client.
import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import path from 'node:path'
import { build } from 'esbuild'
import React from 'react'
import renderer from 'react-test-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const dir = await mkdtemp(path.resolve('.p1-tests-'))
const storage = () => {
  const data = new Map()
  return { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: k => data.delete(k) }
}
globalThis.localStorage = storage()
globalThis.sessionStorage = storage()
let checks = 0
function check(value, label) { assert.ok(value, label); checks++; console.log('OK  ', label) }

try {
  await build({
    entryPoints: ['src/screens/AuthScreens.tsx'], outfile: `${dir}/screen.mjs`,
    bundle: true, format: 'esm', platform: 'node', jsx: 'automatic', packages: 'external',
    plugins: [{ name: 'screen-services', setup(b) {
      b.onResolve({ filter: /\.\.\/(account\/me|auth\/auth|max\/bridge)$/ }, a => ({ path: a.path, namespace: 'mocks' }))
      b.onLoad({ filter: /.*/, namespace: 'mocks' }, a => ({ contents:
        a.path.includes('account/me') ? 'export const resetSettings=()=>{};' :
        a.path.includes('auth/auth') ? `export const randomNickname=()=>"RegressionTestStudent";
          export const fetchInviteRequired=async()=>false;
          export const register=async(...args)=>{globalThis.submittedConsent=args[4];return {id:'test',nickname:'RegressionTestStudent',exam:'ege'}};
          export const currentUser=()=>null; export const login=register; export const loginMax=register; export const loginMaxLink=register;` :
        'export const clearLinkToken=()=>{}; export const maxInitData=()=>""; export const pendingLinkToken=()=>null;', loader: 'js' }))
    } }],
  })
  const { RegisterScreen } = await import(pathToFileURL(`${dir}/screen.mjs`))
  for (const scenario of ['password-then-refuse', 'refuse-then-password', 'password-then-accept', 'default']) {
    let tree
    await renderer.act(async () => { tree = renderer.create(React.createElement(RegisterScreen, { onDone() {}, onLogin() {} })) })
    const password = () => renderer.act(async () => tree.root.findByProps({ type: 'password' }).props.onChange({ target: { value: 'test-only-password' } }))
    const consent = value => renderer.act(async () => tree.root.findByProps({ type: 'checkbox' }).props.onChange({ target: { checked: value } }))
    if (scenario === 'refuse-then-password') { await consent(false); await password() }
    else { await password(); if (scenario !== 'default') await consent(scenario === 'password-then-accept') }
    const visible = tree.root.findByProps({ type: 'checkbox' }).props.checked
    globalThis.submittedConsent = undefined
    await renderer.act(async () => tree.root.findByProps({ className: 'auth2-btn' }).props.onClick())
    check(globalThis.submittedConsent === visible, `registration sends the visible consent: ${scenario}`)
    if (scenario === 'default') check(visible === false, 'consent defaults to false')
    await renderer.act(async () => tree.unmount())
  }

  await build({ stdin: { contents: `export * from './src/auth/auth.ts'; export * from './src/account/me.ts';`, resolveDir: process.cwd(), loader: 'ts' },
    outfile: `${dir}/client.mjs`, bundle: true, format: 'esm', platform: 'node', packages: 'external',
    define: { 'import.meta.env.VITE_BACKEND_URL': '""' } })
  localStorage.setItem('pingo.auth.v1', JSON.stringify({ id: 'legacy-account', nickname: 'LegacyStudent', exam: 'ege' }))
  const client = await import(pathToFileURL(`${dir}/client.mjs`))
  check(client.currentUser() === null, 'legacy account id does not become a session')
  let failing = false
  let remoteConsent = false
  const requests = []
  globalThis.fetch = async (url, init = {}) => {
    const body = init.body ? JSON.parse(init.body) : null
    requests.push({ url, init, body })
    if (failing) return new Response(JSON.stringify({ detail: 'synthetic failure' }), { status: 503 })
    if (url === '/auth/register' || url === '/auth/login') {
      remoteConsent = body.corpus_consent === true
      return Response.json({ id: 'stable-account', nickname: 'RegressionTestStudent', exam: 'ege', session_token: 'gs_' + 'a'.repeat(43), expires_at: Date.now() / 1000 + 3600 })
    }
    if (url === '/me/settings') {
      if (body && 'corpus_consent' in body) remoteConsent = body.corpus_consent
      return Response.json({ settings: { corpus_consent: remoteConsent } })
    }
    return Response.json({ ok: true })
  }
  await client.register('RegressionTestStudent', 'test-only-password', 'ege', '', false)
  check(requests.at(-1).body.corpus_consent === false, 'consent travels in the registration request')
  check(client.authHeaders().Authorization === 'Bearer ' + client.currentUser().session_token, 'requests use a session token')
  check(!('X-Device' in client.authHeaders()), 'account id is not sent as authentication')
  await client.setCorpusConsent(true)
  check(client.getSettings().corpusConsent === true && remoteConsent === true, 'confirmed opt-in is shown')
  failing = true
  await assert.rejects(client.setCorpusConsent(false))
  check(client.getSettings().corpusConsent === true, 'failed withdrawal does not pretend to have saved')
  await assert.rejects(client.logout())
  check(client.currentUser() !== null, 'failed server logout is not reported as successful')
  failing = false
  await client.setCorpusConsent(false)
  client.updateSettings({ volume: 0.3 })
  await new Promise(resolve => setTimeout(resolve, 850))
  check(!('corpus_consent' in requests.at(-1).body), 'delayed volume save never resubmits consent')
  check(remoteConsent === false, 'withdrawal remains in force after appearance changes')
  await client.logout()
  check(client.currentUser() === null, 'successful server logout clears local session')
  check(requests.at(-1).url === '/auth/logout', 'logout calls the revocation endpoint')
  client.resetSettings()
  console.log(`P1 frontend: ${checks} checks passed`)
} finally {
  await rm(dir, { recursive: true, force: true })
}
