import React, {useEffect, useRef, useState} from 'react';

const messages = {
  CANCELLED: 'No sound task was started.',
  PREVIEW_READY: 'Sound preview prepared and checked. Your original is unchanged.',
  INTERRUPTED: 'Sound work stopped. Check saved work before restarting.',
  REVIEW_REQUIRED: 'Sound work needs review. No automatic restart was requested.',
};
export default function NativeAudioPreviewPanel({projectId}) {
  const [catalog, setCatalog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const alive = useRef(false);
  const pending = useRef(false);
  async function load(after = null) {
    try {
      const api = window.pywebview?.api;
      if (typeof api?.audio_preview_catalog !== 'function') return;
      const result = await api.audio_preview_catalog(projectId, after);
      if (alive.current) setCatalog(result?.available === true ? result : null);
    } catch { if (alive.current) setCatalog(null); }
  }
  useEffect(() => {
    alive.current = true;
    const ready = () => load();
    ready(); window.addEventListener('pywebviewready', ready);
    return () => {
      alive.current = false;
      window.removeEventListener('pywebviewready', ready);
      if (pending.current) Promise.resolve(window.pywebview?.api?.audio_preview_cancel(projectId)).catch(() => {});
    };
  }, [projectId]);
  async function start(item) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setNotice('');
    try {
      const result = await window.pywebview.api.audio_preview_start(projectId, item.source_id, item.revision);
      if (alive.current) setNotice(messages[result?.status] || messages.REVIEW_REQUIRED);
    } catch { if (alive.current) setNotice(messages.REVIEW_REQUIRED); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  async function cancel() {
    try {
      const result = await window.pywebview.api.audio_preview_cancel(projectId);
      if (alive.current && pending.current && result?.status === 'CANCELLATION_REQUESTED') setNotice('Stopping sound work…');
    } catch { if (alive.current && pending.current) setNotice('Sound work needs review.'); }
  }
  if (!catalog) return null;
  return <section className="film-card" aria-label="Sound previews">
    <h2>Prepare sound preview</h2>
    <p className="film-muted">Choose a compatible original recording from this movie. Your original remains unchanged.</p>
    {!catalog.items.length && <p>No compatible original sound in this group.</p>}
    {catalog.items.map(item => <div className="film-recovery-row" key={item.source_id}>
      <span>{item.source_id}</span>
      <button className="film-secondary" disabled={busy} onClick={() => start(item)}>Prepare preview</button>
    </div>)}
    {catalog.next_after && <button className="film-secondary" disabled={busy} onClick={() => load(catalog.next_after)}>Next sounds</button>}
    <button className="film-secondary" disabled={busy} onClick={() => load()}>Check sounds</button>
    {busy && <button className="film-secondary" onClick={cancel}>Cancel sound task</button>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
