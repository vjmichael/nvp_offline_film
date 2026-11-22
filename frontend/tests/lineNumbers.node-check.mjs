import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeLineEndings, countSourceLines, formatNumberedSource, formatSelectedSourceLines, lineAtOffset, lineNumberGutter, offsetForSourceLine } from '../src/lineNumbers.js';

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

test('jump-to-line offsets include empty lines and reject invalid targets', () => {
  const source = 'INT. ROOM - DAY\r\n\r\nALEX\r\nWait.\r\n';
  assert.equal(offsetForSourceLine(source, 1), 0);
  assert.equal(offsetForSourceLine(source, 2), 16);
  assert.equal(offsetForSourceLine(source, 3), 17);
  assert.equal(offsetForSourceLine(source, 4), 22);
  assert.equal(offsetForSourceLine(source, 5), 28);
  assert.throws(() => offsetForSourceLine(source, 0), RangeError);
  assert.throws(() => offsetForSourceLine(source, 6), RangeError);
});

test('copy selected lines preserves global references and handles exclusive selection end', () => {
  const source = 'A\n\nB\nC\n';
  assert.equal(formatSelectedSourceLines(source, 2, 4), 'L02 | \nL03 | B');
  assert.equal(formatSelectedSourceLines(source, 0, 2), 'L01 | A');
  assert.equal(formatSelectedSourceLines(source, 5, 5), formatNumberedSource(source));
  assert.equal(formatSelectedSourceLines(source, 6, 6), formatNumberedSource(source));
  assert.throws(() => formatSelectedSourceLines(source, 5, 4), RangeError);
  assert.throws(() => formatSelectedSourceLines(source, -1, 2), RangeError);
  const longSource = Array.from({length:110},(_,i)=>'Line'+(i+1)).join('\n');
  const start = offsetForSourceLine(longSource, 108);
  assert.equal(formatSelectedSourceLines(longSource, start, longSource.length),
    'L108 | Line108\nL109 | Line109\nL110 | Line110');
});
