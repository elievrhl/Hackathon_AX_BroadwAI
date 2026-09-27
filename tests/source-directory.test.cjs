const { test } = require('node:test');
const assert = require('node:assert/strict');
const { selectSources, sourceCSV, safeURL } = require('../broadwai/static/source-directory.js');

const source = { name: 'Science Étonnante', publisher: 'David Louapre', description: 'Mathématiques', topics: ['science'], topicLabels: ['Sciences'], languages: ['fr'], format: 'youtube', selected: true, imported: true };
const filters = { format: 'all', query: '', topic: '', language: '', publisher: '', status: 'imported' };
test('search handles accents and composes language, topic and format filters', () => {
  assert.equal(selectSources([source], {...filters, query:'etonnante', language:'fr', topic:'science', format:'youtube'}).length, 1);
  assert.equal(selectSources([source], {...filters, language:'en'}).length, 0);
  assert.equal(selectSources([source], {...filters, status:'excluded'}).length, 0);
  assert.equal(selectSources([{...source, selected:false}], {...filters, status:'excluded'}).length, 0);
});
test('CSV retains readable French and neutralizes spreadsheet formulas', () => {
  const csv = sourceCSV([{...source, name:'=HYPERLINK("bad")', description:'Un; texte\nà lire'}]);
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes('"\'=HYPERLINK(""bad"")"'));
  assert.ok(csv.includes('"Un; texte\nà lire"'));
});
test('links exclude executable schemes and embedded credentials', () => {
  for (const value of ['javascript:alert(1)', 'file:///x', 'https://name:secret@example.org']) assert.equal(safeURL(value), null);
  assert.equal(safeURL('https://example.org/'), 'https://example.org/');
});
