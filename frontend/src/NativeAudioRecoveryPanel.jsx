import React, {useEffect, useState, useRef} from 'react';

const MESSAGES = {
  CANCELLED: 'No changes were made.',
  RECOVERED: 'Saved sound work was recovered. No new rendering was started.',
  CLOSED: 'The interrupted task is closed. Your original material is unchanged.',
  ENDED: 'The interrupted task was ended without restarting it.',
  REVIEW_REQUIRED: 'This sound work needs further review. It was not restarted.',
};

export default function NativeAudioRecoveryPanel() {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const alive = useRef(false);
  const pending = useRef(false);
  async function refresh(showError = false, page = null) {
    const api = window.pywebview?.api;
    if (typeof api?.audio_recovery_catalog !== 'function') return;
    try {
      const result = await api.audio_recovery_catalog(page);
      if (alive.current) setReport(result?.available === true ? result : null);
    } catch {
      if (alive.current) {
        setReport(null);
        if (showError) setError('Sound work could not be checked. Your saved material is unchanged.');
      }
    }
  }
  useEffect(() => {
    alive.current = true;
    const ready = async () => {
      if (pending.current || typeof window.pywebview?.api?.audio_recovery_catalog !== 'function') return;
      pending.current = true;
      try { await refresh(); } finally { pending.current = false; }
    };
    ready(); window.addEventListener('pywebviewready', ready);
    return () => { alive.current = false; window.removeEventListener('pywebviewready', ready); };
  }, []);
  async function act(selection, action) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const api = window.pywebview?.api;
      if (typeof api?.audio_recovery_act !== 'function') throw Error();
      const result = await api.audio_recovery_act(selection, action);
      if (!Object.hasOwn(MESSAGES, result?.status)) throw Error();
      if (alive.current) setNotice(MESSAGES[result.status]);
    } catch {
      if (alive.current) setError('Sound work needs review. No restart was requested.');
    } finally {
      if (alive.current) await refresh(true);
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  // No native managed authority: do not suggest this action in other clients.
  if (!report && !notice && !error) return null;
  return <section className="film-sections" aria-label="Interrupted sound work">
    <h2>Interrupted sound work</h2>
    <p className="film-muted">Check saved audio after an unexpected interruption. Nothing restarts automatically.</p>
    {report && <>
      {report.items.length === 0 && <p>No recoverable sound tasks in this group.</p>}
      {report.items.map((item, i) => <div className="film-recovery-row" key={item.selection}>
        <span>Interrupted sound task {i + 1}</span>
        {item.can_recover && <button className="film-secondary" disabled={busy} onClick={() => act(item.selection, 'recover')}>Check saved audio</button>}
        {item.can_abandon && <button className="film-secondary" disabled={busy} onClick={() => act(item.selection, 'abandon')}>End interrupted task</button>}
      </div>)}
      {!!report.held && <p>Some sound tasks need further review. They remain paused.</p>}
      {report.more && <button className="film-secondary" disabled={busy} onClick={async () => {
        if (pending.current) return;
        pending.current = true; setBusy(true);
        try { await refresh(true, report.next_page); } finally { pending.current = false; if (alive.current) setBusy(false); }
      }}>Next sound tasks</button>}
      <button className="film-secondary" disabled={busy} onClick={async () => {
        if (pending.current) return;
        pending.current = true; setBusy(true); setError('');
        try { await refresh(true); } finally { pending.current = false; if (alive.current) setBusy(false); }
      }}>Check sound work</button>
    </>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
