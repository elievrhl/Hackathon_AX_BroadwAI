const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function render(brief) {
  const code = fs.readFileSync(require.resolve('../broadwai/static/covers.js'), 'utf8');
  const start = code.indexOf('function renderBrief(');
  const end = code.indexOf('function articleDetails(', start);
  const tables = [], texts = [];
  const context = {
    n: (tag, text) => ({tag, text, append() { if (text) texts.push(text); }}),
    table: (_parent, _headers, rows) => tables.push(rows),
    paragraphs() {}, appendCitedSources() {},
    parent: {append(...nodes) { texts.push(...nodes.map(n => n.text).filter(Boolean)); }},
    brief,
  };
  vm.runInNewContext(code.slice(start, end) + '\nrenderBrief(parent, {brief});', context);
  return {tables, texts};
}

test('admin renders the reusable dossier separately from summary and personalization', () => {
  const result = render({summary: 'Résumé', key_points: [], caveats: [], dossier: {
    contribution: 'Comprendre la méthode', angle: 'Comparaison', prerequisites: 'Bases',
    integrity: 'fragmentary', support: 'method', temporal_kind: 'evergreen',
    temporal_dependency: 'Version 3', central_risk: false,
  }});
  assert.equal(result.tables[0][0][1], 'Comprendre la méthode');
  assert.equal(result.tables[0][3][1], 'Contenu partiel');
  assert.ok(result.texts.some(t => t.includes('pas une certification')));
});

test('legacy briefs still display their old validity without manufacturing a dossier', () => {
  const result = render({summary: 'Ancienne fiche', key_points: [], caveats: [],
    validity: {reason: 'Méthode durable'}});
  assert.equal(result.tables.length, 0);
  assert.ok(result.texts.some(t => t.includes('Méthode durable')));
});
