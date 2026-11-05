import React, { useMemo, useRef, useState } from 'react';
import { countSourceLines, formatNumberedSource, lineAtOffset, lineNumberGutter } from './lineNumbers.js';

/**
 * Plain-text editor with 1-based source line references, including blank lines.
 * A non-wrapping textarea is deliberate: each visual row corresponds to exactly
 * one stable source line, even for unusually long Fountain lines. Horizontal
 * overflow scrolls within the editor. The gutter is never part of `value`.
 */
export default function LineNumberedTextarea({
  value, onChange, rows = 16, maxLength, placeholder = '', label = 'Screenplay text',
}) {
  const editorRef = useRef(null);
  const gutterRef = useRef(null);
  const [cursorLine, setCursorLine] = useState(1);
  const [copyStatus, setCopyStatus] = useState('');
  const lineCount = useMemo(() => countSourceLines(value), [value]);
  const gutter = useMemo(() => lineNumberGutter(lineCount), [lineCount]);
  const gutterWidth = Math.max(3, String(lineCount).length + 2);

  function syncScroll(event) {
    if (gutterRef.current) gutterRef.current.scrollTop = event.currentTarget.scrollTop;
  }

  function updateCursor(event) {
    setCursorLine(lineAtOffset(event.currentTarget.value, event.currentTarget.selectionStart));
  }

  async function copyNumbered() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(formatNumberedSource(value));
      setCopyStatus('Numbered reference copied; your saved screenplay is unchanged.');
    } catch {
      setCopyStatus('Unable to copy automatically. Select your text and copy manually.');
    }
  }

  return <div className="line-numbered-container">
    <div className="line-numbered-editor" style={{
      '--line-editor-height': `${Math.max(5, rows) * 1.55 + 2.4}em`,
      '--gutter-width': `${gutterWidth}ch`,
    }}>
      <div ref={gutterRef} className="line-numbered-gutter" aria-hidden="true">{gutter}</div>
      <textarea ref={editorRef} className="line-numbered-input" aria-label={label}
        wrap="off" spellCheck={false} value={value} onChange={onChange}
        onScroll={syncScroll} onClick={updateCursor} onKeyUp={updateCursor}
        onSelect={updateCursor} maxLength={maxLength} placeholder={placeholder}/>
    </div>
    <div className="line-numbered-footer">
      <span>Line {Math.min(cursorLine, lineCount)} of {lineCount} · 1-based · no line numbers saved</span>
      <button type="button" className="secondary" onClick={copyNumbered}>Copy with line numbers for AI</button>
    </div>
    {copyStatus && <p role="status" className="line-numbered-status">{copyStatus}</p>}
  </div>;
}
