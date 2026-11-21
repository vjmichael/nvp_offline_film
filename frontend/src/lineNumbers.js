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

/** Return a 0-based UTF-16 caret offset for a 1-based source line. */
export function offsetForSourceLine(value, targetLine) {
  if (!Number.isSafeInteger(targetLine) || targetLine < 1) {
    throw new RangeError('Source line must be a positive integer');
  }
  const text = normalizeLineEndings(value);
  if (targetLine === 1) return 0;
  let line = 1;
  for (let offset = 0; offset < text.length; offset += 1) {
    if (text[offset] === '\n' && ++line === targetLine) return offset + 1;
  }
  throw new RangeError('Source line is beyond the end of the document');
}

/**
 * Export complete selected source lines with their ORIGINAL global line numbers.
 * Selection end is exclusive, like HTML textarea.selectionEnd. An unselected
 * caret exports the whole document, matching the existing copy action.
 */
export function formatSelectedSourceLines(value, selectionStart = 0, selectionEnd = 0) {
  const text = normalizeLineEndings(value);
  if (!Number.isSafeInteger(selectionStart) || !Number.isSafeInteger(selectionEnd)
      || selectionStart < 0 || selectionEnd < selectionStart || selectionEnd > text.length) {
    throw new RangeError('Invalid source selection');
  }
  if (selectionStart === selectionEnd) return formatNumberedSource(text);
  const firstLine = lineAtOffset(text, selectionStart);
  // Avoid accidentally including the next line when selection ends exactly
  // after a newline; the end of a browser selection is exclusive.
  const lastLine = lineAtOffset(text, selectionEnd - 1);
  const lines = text.split('\n');
  const width = Math.max(2, String(lines.length).length);
  return lines.slice(firstLine - 1, lastLine)
    .map((line, i) => 'L' + String(firstLine + i).padStart(width, '0') + ' | ' + line)
    .join('\n');
}
