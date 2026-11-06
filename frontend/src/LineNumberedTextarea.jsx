import React, { useMemo, useRef, useState } from 'react';
import { countSourceLines, formatSelectedSourceLines, lineAtOffset, lineNumberGutter, offsetForSourceLine } from './lineNumbers.js';

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
  const goInputRef = useRef(null);
  const [cursorLine, setCursorLine] = useState(1);
  const [copyStatus, setCopyStatus] = useState('');
  const [goLine, setGoLine] = useState('');
  const lineCount = useMemo(() => countSourceLines(value), [value]);
  const gutter = useMemo(() => lineNumberGutter(lineCount), [lineCount]);
  const gutterWidth = Math.max(3, String(lineCount).length + 2);

  function syncScroll(event) {
    if (gutterRef.current) gutterRef.current.scrollTop = event.currentTarget.scrollTop;
  }

  function updateCursor(event) {
    setCursorLine(lineAtOffset(event.currentTarget.value, event.currentTarget.selectionStart));
  }

  function jumpToLine() {
    const target = Number(goLine);
    if (!Number.isSafeInteger(target) || target < 1 || target > lineCount) {
      setCopyStatus('Enter a line between 1 and ' + lineCount + '.');
      return;
    }
    const editor = editorRef.current;
    if (!editor) return;
    const offset = offsetForSourceLine(value, target);
    editor.focus();
    editor.setSelectionRange(offset, offset);
    const lineHeight = parseFloat(window.getComputedStyle(editor).lineHeight);
    if (Number.isFinite(lineHeight) && lineHeight > 0) {
      editor.scrollTop = Math.max(0, (target - 1) * lineHeight - editor.clientHeight / 3);
      if (gutterRef.current) gutterRef.current.scrollTop = editor.scrollTop;
    }
    setCursorLine(target);
    setCopyStatus('');
  }

  async function copyNumbered() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      const editor = editorRef.current;
      const start = editor?.selectionStart ?? 0;
      const end = editor?.selectionEnd ?? 0;
      await navigator.clipboard.writeText(formatSelectedSourceLines(value, start, end));
      const first = lineAtOffset(value, start);
      const last = lineAtOffset(value, end > start ? end - 1 : end);
      const scope = end > start ? 'source lines ' + first + '–' + last : 'all source lines';
      setCopyStatus('Copied ' + scope + ' with references; saved text is unchanged.');
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
        onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'g') {
          event.preventDefault(); goInputRef.current?.focus();
        } }}
        onSelect={updateCursor} maxLength={maxLength} placeholder={placeholder}/>
    </div>
    <div className="line-numbered-footer">
      <span>Line {Math.min(cursorLine, lineCount)} of {lineCount} · 1-based · no line numbers saved</span>
      <div className="line-numbered-actions">
        <label className="line-numbered-go-label">Go to line
          <input ref={goInputRef} aria-label="Go to source line" type="number" min="1" max={lineCount}
            value={goLine} onChange={(event) => setGoLine(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); jumpToLine(); } }}/>
        </label>
        <button type="button" className="secondary" onClick={jumpToLine}>Go</button>
        <button type="button" className="secondary" onClick={copyNumbered}>Copy selection / all for AI</button>
      </div>
    </div>
    {copyStatus && <p role="status" className="line-numbered-status">{copyStatus}</p>}
  </div>;
}
