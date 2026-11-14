# NVP screenplay source-line references

**Implemented:** screenwriter UI line numbers and line-referenced screenplay context for the local writing assistant.

## Where the numbers appear

- New project: import or paste a Fountain / TXT screenplay.
- Develop: edit a **screenplay-stage** proposed draft.
- Screenplay: edit the creator's actual saved screenplay.
- Review screenplay: expand the source-scene excerpt. Its labels use the **global screenplay** `start_line` from the original parser.

The source gutter is 1-based. Blank lines and a trailing newline count as lines; CRLF and CR inputs are normalized for reference computation to match the parser and HTML textarea. The input uses `wrap="off"` so that physical lines and displayed numbers never drift when words wrap; long lines can be scrolled horizontally. The vertical gutter scrolls with the editor.

The current cursor line and total line count are displayed below the editor. The **Go to line** field accepts a one-based source line and moves the caret there without changing the screenplay; `Ctrl+G` or `Cmd+G` focuses the field. The gutter follows vertical scrolling. **Copy selection / all for AI** exports complete original source lines for any nonempty selection, or the entire screenplay when no text is selected. Selection end is exclusive (a selection ending at the first character of the next line does not include that line). Numbered output retains original global line references; the clipboard result never becomes saved screenplay text. Example:

```text
L01 | INT. KITCHEN - NIGHT
L02 |
L03 | ALEX
L04 | Wait.
```

## Data safety and AI contract

These numbers are **view and prompt references only**. They are never inserted into:

- the editable screenplay's `value`,
- the saved Fountain source,
- SQLite project screenplay history,
- original import file content, or
- a creator-approved AI proposal.

When NVP sends existing screenplay context to its local writing model, source lines are prefixed with the same `LNN | ` convention; a selected scene begins with its **original full-script** line index. The system prompt explicitly instructs the model to use such labels only as locators and omit them from generated Fountain output.

Number references are **revision-relative**, not persistent document IDs. If lines are inserted or deleted, downstream line numbers can shift. Use the screenplay revision (and, where applicable, the scene ID) to disambiguate historical notes. The existing source-excerpt truncation guard remains intact; the model must not claim to have seen omitted lines.

## Implementation

- `frontend/src/LineNumberedTextarea.jsx` — reusable plain-text editor.
- `frontend/src/lineNumbers.js` — line counting, caret mapping and numbered source export.
- `frontend/src/index.css` — synchronized gutter and source-preview presentation.
- `frontend/src/App.jsx`, `ScreenplayReviewPanel.jsx` — wired into screenplay screens.
- `backend/nvp_story_context.py` — numbered, read-only AI screenplay excerpts.

## Regression commands

```bash
node --test frontend/tests/lineNumbers.node-check.mjs
python -m unittest tests.test_studio tests.test_story_context tests.test_screenplay_review tests.test_idea_pipeline -q
cd frontend && node node_modules/vite/bin/vite.js build
```

Validated in the Debian development container: 5 Node source-line checks, 57 Python screenplay/story tests, and a successful Vite production compile (55 transformed modules).

**Not yet verified:** interactive Chromium/WebView2 UI acceptance. The local sandbox browser blocked navigation even to loopback and file/data pages, so scroll position and native clipboard must be smoke-tested in the installed Windows app. The offline frontend toolchain currently uses React 19 as recovered from Lu's Yarn cache, although `frontend/package.json` declares React 18; check this version mismatch before final Windows release.

The Windows NSIS installer status is independent of this feature.

### Follow-on navigation acceptance (2026-11-05)

- Jump to an existing first, blank, middle, or trailing source line; reject zero and out-of-range destinations.
- Select text crossing blank lines and copy exact global source-line references. When selection ends at a newline boundary, omit the unselected next line.
- Repeat with CRLF imports and more than 100 lines; verify emitted line labels and original Fountain text remain intact.
- Browser validation in the Debian tool session remains **not accepted**: Chromium was denied access to loopback with ERR_BLOCKED_BY_ADMINISTRATOR; run interactive UI acceptance in the installed Windows client.
