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

function renderDecisions(events, trace = []) {
  const code = fs.readFileSync(require.resolve('../broadwai/static/covers.js'), 'utf8');
  const start = code.indexOf('function renderDecisions(');
  const end = code.indexOf('function renderEdition(', start);
  const texts = [];
  const parent = {append(...nodes) { texts.push(...nodes.map(n => n.text).filter(Boolean)); }};
  vm.runInNewContext(code.slice(start, end) + '\nrenderDecisions(parent, cover, data);', {
    parent, cover: {trace}, data: {events},
    section: () => parent, n: (_tag, text) => ({text}),
    actionNames: {}, paragraphs() {}, jsonDetails: () => ({}),
  });
  return texts.join(' ');
}

test('admin explains broad scope and labels the actual search angle', () => {
  const text = renderDecisions([
    {kind: 'research_completed'}, {kind: 'selection_policy', allow_adjacent: true},
  ], [{step: -1, action: 'search_web', justification: 'Changer de piste', outcome: {
    actor: 'controller', query: 'spectroscopie stellaire', added_ids: [],
    search_angle: {scope: 'depth', connection: 'Comprendre les mesures stellaires'},
  }}]);
  assert.match(text, /25 % des articles effectivement retenus/);
  assert.match(text, /Approfondissement du domaine · Comprendre les mesures stellaires/);
  assert.match(text, /plafonds entre intérêts sont souples/);
});

test('admin does not claim a closed or legacy profile permits adjacent topics', () => {
  const closed = renderDecisions([{kind: 'selection_policy', allow_adjacent: false}]);
  assert.match(closed, /Exploration désactivée/);
  assert.doesNotMatch(closed, /25 %/);
  assert.doesNotMatch(renderDecisions([]), /Périmètre élargi/);
});
