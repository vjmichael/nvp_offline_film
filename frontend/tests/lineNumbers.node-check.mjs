import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeLineEndings, countSourceLines, formatNumberedSource, lineAtOffset, lineNumberGutter } from '../src/lineNumbers.js';

test('counts blank lines, trailing newline, and Windows CRLF correctly', () => {
  assert.equal(countSourceLines(''), 1);
  assert.equal(countSourceLines('INT. HALL - DAY\n\nAction\n'), 4);
  assert.equal(countSourceLines('INT. HALL - DAY\r\n\r\nAction\r\n'), 4);
  assert.equal(countSourceLines('A\rB'), 2);
});

test('stable one-based gutter and cursor location', () => {
  assert.equal(lineNumberGutter(4), '1\n2\n3\n4');
  assert.equal(lineAtOffset('A\n\nB', 0), 1);
  assert.equal(lineAtOffset('A\n\nB', 2), 2);
  assert.equal(lineAtOffset('A\n\nB', 3), 3);
});

test('numbered copy preserves original punctuation and blank source lines', () => {
  const original='INT. KITCHEN - NIGHT\r\n\r\nALEX\r\nIt is ready.';
  assert.equal(formatNumberedSource(original),
    'L01 | INT. KITCHEN - NIGHT\nL02 | \nL03 | ALEX\nL04 | It is ready.');
  assert.equal(original, 'INT. KITCHEN - NIGHT\r\n\r\nALEX\r\nIt is ready.');
  assert.equal(normalizeLineEndings('A\r\nB\rC'), 'A\nB\nC');
  assert.equal(formatNumberedSource('A\n', 120), 'L120 | A\nL121 | ');
  assert.throws(() => formatNumberedSource('A', 0), RangeError);
});
