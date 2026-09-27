const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8');

function startApp(respond) {
  const dom = new JSDOM(html, { url: 'http://localhost/', runScripts: 'outside-only' });
  const calls = [];
  dom.window.fetch = async (endpoint, options) => {
    calls.push({ endpoint, body: options?.body && JSON.parse(options.body) });
    return { ok: true, json: async () => respond(endpoint) };
  };
  dom.window.confirm = () => true;
  dom.window.eval(script);
  dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));
  return { window: dom.window, calls, close: () => dom.window.close() };
}

test('fridge and expiry use the same local inventory without hOn polling', async () => {
  const app = startApp((endpoint) => {
    if (endpoint.endsWith('/fridge_inventory_list')) {
      return { ok: true, data: { items: [
        { id: 42, name: 'Milk', position: 'fridge', quantity: 1, unit: 'pz', expires_on: '2099-01-01' },
      ] } };
    }
    throw new Error(`Unexpected endpoint: ${endpoint}`);
  });
  try {
    await app.window.App.loadFridge();
    assert.match(app.window.document.querySelector('#view').textContent, /Milk/);
    assert.equal(app.calls.filter(({ endpoint }) => endpoint.endsWith('/fridge_inventory_list')).length, 1);
    assert.equal(app.calls.filter(({ endpoint }) => endpoint.endsWith('/inventory_expiring')).length, 0);
  } finally { app.close(); }
});

test('fridge errors show recovery instead of claiming the fridge is empty', async () => {
  const app = startApp(() => ({ ok: false, error: 'Server unavailable' }));
  try {
    await app.window.App.loadFridge();
    const text = app.window.document.querySelector('#view').textContent;
    assert.match(text, /Couldn't load fridge/);
    assert.match(text, /Server unavailable/);
    assert.doesNotMatch(text, /Fridge is empty/);
  } finally { app.close(); }
});

test('cloud import only happens after the explicit action', async () => {
  const app = startApp(() => ({ ok: true, data: { imported: 1, skipped: 0, items: [] } }));
  try {
    await app.window.App.loadFridge();
    assert.equal(app.calls.filter(({ endpoint }) => endpoint.endsWith('/fridge_inventory_import_hon')).length, 0);
    await app.window.App.importHon();
    await new Promise(setImmediate);
    assert.equal(app.calls.filter(({ endpoint }) => endpoint.endsWith('/fridge_inventory_import_hon')).length, 1);
  } finally { app.close(); }
});

test('chat sends only text, not redundant history', async () => {
  const app = startApp(() => ({ reply: 'Hello' }));
  try {
    await app.window.App.sendChat('Hello');
    const chat = app.calls.find(({ endpoint }) => endpoint === '/api/chat');
    assert.deepEqual(Object.keys(chat.body), ['text']);
  } finally { app.close(); }
});
