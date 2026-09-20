import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

export async function run() {
  const code = await readFile(new URL('../script.js', import.meta.url), 'utf8');
  const saved = new Map();
  let creates = 0;
  let answerRequests = [];
  let failImages = false;
  const items = Array.from({ length: 15 }, (_, i) => ({ image_id: `opaque-${i}`, src: `/api/media/opaque-${i}` }));
  function boot() {
    const elements = new Map();
    const genders = [{ value: 'other', checked: false }];
    function element(key) {
      if (!elements.has(key)) elements.set(key, {
        value: '', disabled: false, textContent: '', handlers: {},
        classList: { add() {}, remove() {} }, removeAttribute() {},
        addEventListener(name, handler) { this.handlers[name] = handler; },
      });
      return elements.get(key);
    }
    const form = element('#test-form');
    form.elements = { answer: { value: '' }, confidence: { value: '' } };
    form.reset = () => { form.elements.answer.value = ''; form.elements.confidence.value = ''; };
    const fetch = async (url, options) => {
      let data;
      let status = 200;
      if (url === '/api/participants') { creates++; data = { participant_id: 'participant-1' }; }
      else if (url.startsWith('/api/images')) {
        if (failImages) throw Error('network');
        data = items;
      } else if (url.startsWith('/api/quiz/')) data = { next_index: answerRequests.length };
      else if (url === '/api/answers') { answerRequests.push(JSON.parse(options.body)); data = { success: true }; }
      else throw Error(`Unexpected URL: ${url}`);
      return { ok: status === 200, status, json: async () => data };
    };
    vm.runInNewContext(code, {
      document: { querySelector: element, querySelectorAll: () => genders },
      localStorage: { getItem: k => saved.get(k), setItem: (k,v) => saved.set(k,v), removeItem: k => saved.delete(k) },
      console: { info() {}, error() {} }, fetch, quizApi: { request: fetch, reset() {} },
    });
    return { element, form, genders };
  }
  const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
  const event = { preventDefault() {} };
  let ui = boot();
  ui.element('#age').value = '25'; ui.genders[0].checked = true; ui.element('#experience').value = 'daily';
  failImages = true;
  await ui.element('#intro-form').handlers.submit(event);
  assert.equal(creates, 1);
  failImages = false;
  await ui.element('#intro-form').handlers.submit(event);
  assert.equal(creates, 1, 'Image retry must reuse the participant');
  assert.equal(ui.element('#test-image').src, items[0].src);
  ui.form.elements.answer.value = 'ai'; ui.form.elements.confidence.value = '5'; ui.element('#ai-reason').value = 'Test reason';
  const first = ui.form.handlers.submit(event);
  await ui.form.handlers.submit(event);
  await first;
  assert.equal(answerRequests.length, 1, 'Double submit must be ignored');
  assert.equal(answerRequests[0].image_id, 'opaque-0');
  assert.equal(answerRequests[0].confidence, 5);
  assert.equal(answerRequests[0].ai_reason, 'Test reason');
  ui = boot(); await flush();
  assert.equal(creates, 1);
  assert.equal(ui.element('#test-image').src, items[1].src, 'Reload must resume first unanswered image');
  for (let i = 1; i < 15; i++) {
    ui.form.elements.answer.value = 'photo'; ui.form.elements.confidence.value = '3';
    await ui.form.handlers.submit(event);
  }
  assert.equal(answerRequests.length, 15);
  assert.match(ui.form.innerHTML, /uloženy/);
  ui = boot(); await flush();
  assert.match(ui.form.innerHTML, /uloženy/, 'Completed quiz stays completed after reload');
  assert.equal(creates, 1);
  return 'Frontend OK: retries, double-submit protection, image identity, confidence, resume and completion';
}
