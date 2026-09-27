import test from 'node:test';
import assert from 'node:assert/strict';
import { EVENTS_CATALOG } from './events-catalog.js';
import { eligibleEvent, eventDateLabel, selectEvents, parisDay } from './events.js';
import { TOPICS } from './reader.js';

const now = new Date('2026-09-27T12:00:00Z');
const profile = { topics: ['tech', 'economy', 'world'], languages: ['fr', 'en'] };
const sample = {
  id: 'sample', title: 'Sample', topics: ['tech'], provider: 'Museum', kind: 'exhibition',
  mode: 'out', area: 'paris', language: 'fr', checkedOn: '2026-09-27',
  startsOn: '2026-09-01', endsOn: '2026-10-01', url: 'https://example.org/event',
};

test('outings require a known date, matching area, language and a current 14-day window', () => {
  assert.equal(eligibleEvent(sample, { now }), true);
  for (const patch of [
    { endsOn: '2026-09-26' }, { endsOn: null }, { endsOn: '2026-09-31' },
    { startsOn: '2026-10-12', endsOn: '2026-10-13' }, { startsOn: '2026-10-02' },
    { area: 'lyon' }, { cancelled: true }, { unavailable: true }, { language: 'de' },
    { url: 'javascript:alert(1)' }, { url: 'https://name:secret@example.org/' },
  ]) assert.equal(eligibleEvent({ ...sample, ...patch }, { now }), false, JSON.stringify(patch));
  assert.equal(eligibleEvent({ ...sample, startsOn: '2026-10-11', endsOn: '2026-10-12' }, { now }), true);
  assert.equal(eligibleEvent(sample, { now, area: '' }), false);
  assert.equal(eligibleEvent({ ...sample, startsOn: undefined }, { now }), true);
});

test('expiry uses the Paris calendar including daylight saving, not the browser timezone', () => {
  assert.equal(parisDay(new Date('2026-09-30T22:00:00Z')), '2026-10-01');
  assert.equal(eligibleEvent(sample, { now: new Date('2026-10-01T21:59:59Z') }), true);
  assert.equal(eligibleEvent(sample, { now: new Date('2026-10-01T22:00:00Z') }), false);
  const winter = { ...sample, endsOn: '2026-11-01' };
  assert.equal(eligibleEvent(winter, { now: new Date('2026-11-01T22:59:59Z') }), true);
  assert.equal(eligibleEvent(winter, { now: new Date('2026-11-01T23:00:00Z') }), false);
});

test('dated performances advance to the next session and disappear at the last start', () => {
  const concert = EVENTS_CATALOG.find(item => item.id === 'chailly-orchestre-paris');
  const between = new Date('2026-09-30T20:00:00+02:00');
  assert.equal(eligibleEvent(concert, { now: between }), true);
  assert.match(eventDateLabel(concert, between), /1 octobre.*20:00/);
  assert.equal(eligibleEvent(concert, { now: new Date('2026-10-01T20:00:00+02:00') }), false);
  const festival = EVENTS_CATALOG.find(item => item.id === 'fete-science-arts-metiers');
  assert.equal(eligibleEvent(festival, { now: new Date('2026-10-04T18:00:00+02:00') }), false);
});

test('online archives do not expire by publication age or require a city', () => {
  const archive = EVENTS_CATALOG.find(item => item.id === 'condition-artiste');
  assert.equal(eligibleEvent(archive, { now, area: '' }), true);
  assert.match(eventDateLabel(archive, now), /Archive du 15 octobre 2018/);
  assert.equal(eligibleEvent({ ...archive, availableUntil: '2026-09-26' }, { now }), false);
  assert.equal(eligibleEvent({ ...archive, availableFrom: '2026-10-01' }, { now }), false);
});

test('recommendations stay relevant and vary formats and providers without paid dependencies', () => {
  const selected = selectEvents(profile, { now });
  assert.equal(selected.length, 6);
  assert.equal(new Set(selected.map(item => item.id)).size, 6);
  assert.ok(new Set(selected.map(item => item.kind)).size >= 3);
  assert.equal(new Set(selected.map(item => item.mode)).size, 2);
  for (const item of selected) {
    assert.ok(item.matches.some(topic => profile.topics.includes(topic)));
    assert.ok(selected.filter(other => other.provider === item.provider).length <= 2);
    assert.ok(item.reason.includes(TOPICS.find(topic => topic.id === item.matches[0]).label));
  }
  assert.deepEqual(selectEvents({ topics: ['sports'], languages: ['fr'] }, { now }), []);
  assert.deepEqual(selectEvents(null, { now }), []);
  assert.ok(selectEvents({ topics: ['music'], languages: ['fr'] }, { now }).every(item => item.topics.includes('music')));
});

test('format filters run before selection, duplicate links are removed and input is immutable', () => {
  const snapshot = JSON.stringify(EVENTS_CATALOG);
  for (const [format, check] of [['out', item => item.mode === 'out'], ['watch', item => item.kind === 'show'], ['listen', item => item.kind === 'podcast']]) {
    const selected = selectEvents(profile, { now, format });
    assert.ok(selected.length > 0);
    assert.ok(selected.every(check));
  }
  assert.equal(selectEvents(profile, { now, catalog: [sample, { ...sample, id: 'duplicate-url' }] }).length, 1);
  assert.equal(JSON.stringify(EVENTS_CATALOG), snapshot);
});

test('prepared catalogue has unique identifiers, source links, supported topics and eligible entries at review', () => {
  assert.equal(new Set(EVENTS_CATALOG.map(item => item.id)).size, EVENTS_CATALOG.length);
  assert.equal(new Set(EVENTS_CATALOG.map(item => item.url)).size, EVENTS_CATALOG.length);
  for (const item of EVENTS_CATALOG) {
    assert.ok(eligibleEvent(item, { now }), item.id);
    assert.ok(item.topics.every(topic => TOPICS.some(known => known.id === topic)), item.id);
    assert.ok(item.description && item.venue && item.practical, item.id);
  }
});
