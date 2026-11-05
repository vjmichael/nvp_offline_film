/**
 * Source line references are 1-based and ephemeral. They never become part of
 * Fountain/script content or saved screenplay revisions.
 *
 * Match the screenplay parser's CRLF/CR handling for imported plain text.
 */
export function normalizeLineEndings(value) {
  return String(value ?? '').replace(/\r\n?/g, '\n');
}

export function countSourceLines(value) {
  const text = normalizeLineEndings(value);
  let count = 1;
  for (const char of text) if (char === '\n') count += 1;
  return count;
}

export function formatNumberedSource(value, startLine = 1) {
  if (!Number.isSafeInteger(startLine) || startLine < 1) {
    throw new RangeError('startLine must be a positive integer');
  }
  const lines = normalizeLineEndings(value).split('\n');
  const width = Math.max(2, String(startLine + lines.length - 1).length);
  return lines.map((line, offset) =>
    `L${String(startLine + offset).padStart(width, '0')} | ${line}`).join('\n');
}

export function lineAtOffset(value, offset) {
  const text = normalizeLineEndings(value);
  const position = Math.max(0, Math.min(text.length, Number.isFinite(offset) ? offset : 0));
  let line = 1;
  for (let i = 0; i < position; i += 1) if (text[i] === '\n') line += 1;
  return line;
}

export function lineNumberGutter(lineCount) {
  return Array.from({ length: lineCount }, (_, i) => String(i + 1)).join('\n');
}
