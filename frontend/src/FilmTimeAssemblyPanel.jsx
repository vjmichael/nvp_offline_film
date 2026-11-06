import React,{useEffect,useRef,useState} from 'react';
import {filmTimeClock} from './FilmTimeIndexPanel.jsx';

// INDEX-TIME-07 — simple human-first assembly, exact original source ranges.
// This is metadata editing. An OS-level native confirmation guards a new
// immutable FilmIndex revision, never source movie edits or a rendered master.
const FORMAT='nvp.index_time07.assembly_plan.v1';

export default function FilmTimeAssemblyPanel({
  projectId,edit,clips,edits,native,onSaved,
}){
  const [draft,setDraft]=useState(null);
  const [change,setChange]=useState(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [chosen,setChosen]=useState(0);
  const [trimIn,setTrimIn]=useState('');
  const [trimOut,setTrimOut]=useState('');
  const [gap,setGap]=useState('0');
  const [sourceEdit,setSourceEdit]=useState('');
  const [sourceOrdinal,setSourceOrdinal]=useState('0');
  const [insertAt,setInsertAt]=useState('0');
  const generation=useRef(0);
  const current=clips.find(c=>c.ordinal===chosen);
  const other=edits.find(e=>e.edit_id===sourceEdit);

  useEffect(()=>{
    generation.current+=1;setDraft(null);setChange(null);setMessage('');
    setChosen(0);setSourceEdit('');setSourceOrdinal('0');
    setInsertAt('0');setTrimIn('');setTrimOut('');setGap('0');
  },[projectId,edit.edit_id,edit.revision,edit.edit_document_sha256]);

  useEffect(()=>{
    setTrimIn(current?.source_in_frame_zero||'');
    setTrimOut(current?.source_out_frame_zero||'');
    if(current){
      const prev=clips.find(c=>c.ordinal===chosen-1);
      const before=prev?.film_end_tick||'0';
      setGap((BigInt(current.film_start_tick)-BigInt(before)).toString());
    }
  },[chosen,clips]);

  async function preview(operation){
    if(busy||!native)return;
    const request=++generation.current;
    setDraft(null);setChange(null);setMessage('');setBusy(true);
    try{
      const input={
        project_id:projectId,edit_id:edit.edit_id,
        edit_revision:edit.revision,
        edit_document_sha256:edit.edit_document_sha256,
        change:operation,
      };
      const answer=await native.preview_footage_assembly(input);
      if(generation.current!==request)return;
      if(answer?.format!==FORMAT ||
         answer.source_revision!==edit.revision ||
         answer.source_document_sha256!==edit.edit_document_sha256 ||
         answer.project_id!==projectId ||
         answer.edit_id!==edit.edit_id ||
         answer.original_sources_modified!==false ||
         answer.approved_final_master!==false ||
         !/^[a-f0-9]{64}$/.test(answer.plan_sha256||'') ||
         !Array.isArray(answer.placements))
        throw new Error('The source assembly changed or could not be prepared.');
      setChange(operation);setDraft(answer);
    }catch(err){
      if(generation.current===request)setMessage(err.message);
    }finally{
      if(generation.current===request)setBusy(false);
    }
  }

  async function save(){
    if(busy||!draft||!change||!native)return;
    const request=++generation.current;
    setBusy(true);setMessage('');
    try{
      const result=await native.save_footage_assembly({
        project_id:projectId,edit_id:edit.edit_id,
        edit_revision:edit.revision,
        edit_document_sha256:edit.edit_document_sha256,
        change,plan_sha256:draft.plan_sha256,
      });
      if(generation.current!==request)return;
      if(result?.format!==FORMAT ||
         result.status!=='SAVED_NEW_EDIT_REVISION' ||
         result.project_id!==projectId ||
         result.edit_id!==edit.edit_id ||
         result.revision!==edit.revision+1 ||
         !/^[a-f0-9]{64}$/.test(result.edit_document_sha256||'') ||
         result.original_sources_modified!==false ||
         result.previous_revision_preserved!==true ||
         result.approved_final_master!==false)
        throw new Error(result?.status==='DENIED'
          ?'The new edit was not approved. Your current version is unchanged.'
          :'The editor needs to reload the current source revision.');
      setDraft(null);setChange(null);
      onSaved(edit.edit_id,result.revision);
    }catch(err){
      if(generation.current===request)setMessage(err.message);
    }finally{
      if(generation.current===request)setBusy(false);
    }
  }

  const max=edit.clip_count;
  const buttonsReady=!busy && !draft && max<=256 && max>0;
  return <section className="card" aria-label="Original footage assembly editor">
    <h3>Arrange source footage</h3>
    <p className="fineprint">Cut, copy, reorder, trim, insert or space clips.
      Save a new version of the assembly; original recordings and earlier
      versions are never changed. No movie is rendered here.</p>
    {max>256&&<p role="alert">
      This initial editor supports up to 256 source clips in one operation.</p>}
    {max<=256&&<>
      <label>Clip to edit
        <select aria-label="Assembly clip" value={current?chosen:''}
          onChange={e=>{setDraft(null);setChange(null);
                        setChosen(Number(e.target.value));}}>
          {clips.map(c=><option key={c.ordinal} value={c.ordinal}>
            {c.ordinal+1}. {c.source_id} · {filmTimeClock(c.film_start_tick)}
          </option>)}
        </select>
      </label>
      {current&&<>
        <div className="actions">
          <button disabled={!buttonsReady||chosen===0}
            onClick={()=>preview({
              operation:'move',index:chosen,target:chosen-1,
            })}>Move earlier</button>
          <button disabled={!buttonsReady||chosen>=max-1}
            onClick={()=>preview({
              operation:'move',index:chosen,target:chosen+2,
            })}>Move later</button>
          <button disabled={!buttonsReady}
            onClick={()=>preview({
              operation:'copy',index:chosen,target:chosen+1,
            })}>Duplicate placement</button>
          <button disabled={!buttonsReady||max===1}
            onClick={()=>preview({operation:'remove',index:chosen})}>
            Remove from assembly</button>
        </div>
        <div className="columns">
          <div>
            <label>Original first frame (inclusive)
              <input aria-label="Trim source in" value={trimIn}
                onChange={e=>setTrimIn(e.target.value)} />
            </label>
            <label>Original end frame (exclusive)
              <input aria-label="Trim source out" value={trimOut}
                onChange={e=>setTrimOut(e.target.value)} />
            </label>
            <button disabled={!buttonsReady}
              onClick={()=>preview({
                operation:'trim',index:chosen,
                source_in_frame_zero:trimIn,
                source_out_frame_zero:trimOut,
              })}>Preview trim</button>
          </div>
          <div>
            <label>Gap before clip (exact Film Time ticks)
              <input aria-label="Gap before source clip" value={gap}
                onChange={e=>setGap(e.target.value)} />
            </label>
            <button disabled={!buttonsReady}
              onClick={()=>preview({
                operation:'set_gap',index:chosen,gap_before_tick:gap,
              })}>Preview spacing</button>
          </div>
        </div>
      </>}
      <h4>Insert a clip from an indexed source edit</h4>
      <p className="fineprint">Choose an existing original-source placement.
        Insert a reference; never copy the movie file.</p>
      <div className="columns">
        <label>Indexed source edit
          <select aria-label="Insert from indexed edit" value={sourceEdit}
            onChange={e=>setSourceEdit(e.target.value)}>
            <option value="">Select source edit…</option>
            {edits.map(e=><option key={e.edit_id} value={e.edit_id}>
              {e.edit_id} · revision {e.revision}
            </option>)}
          </select>
        </label>
        <label>Clip ordinal in source edit (zero-based)
          <input aria-label="Insert source ordinal" value={sourceOrdinal}
            onChange={e=>setSourceOrdinal(e.target.value)}/>
        </label>
        <label>Insert before placement slot (zero-based)
          <input aria-label="Assembly insert slot" value={insertAt}
            onChange={e=>setInsertAt(e.target.value)}/>
        </label>
      </div>
      <button disabled={!buttonsReady||!other}
        onClick={()=>{
          if(!/^\d{1,3}$/.test(sourceOrdinal)||!/^\d{1,3}$/.test(insertAt)){
            setMessage('Use a bounded nonnegative clip ordinal and insertion slot.');
            return;
          }
          preview({
            operation:'insert',target:Number(insertAt),
            source_edit_id:other.edit_id,
            source_edit_revision:other.revision,
            source_edit_sha256:other.edit_document_sha256,
            source_ordinal:Number(sourceOrdinal),
          });
        }}>Preview insert from source edit</button>
      {edit.revision>1&&<div className="actions">
        <button disabled={!buttonsReady}
          onClick={()=>preview({
            operation:'restore',from_revision:edit.revision-1,
          })}>Restore previous arrangement as a new revision</button>
      </div>}
      {draft&&<>
        <h4>Proposed new assembly · revision {draft.next_revision}</h4>
        <p>Clip references: {draft.clip_count} · duration:
          {' '}{filmTimeClock(draft.duration_tick)}
          {' '}({draft.duration_tick} exact ticks)</p>
        <p className="fineprint">Plan SHA: {draft.plan_sha256}</p>
        <ol>
          {draft.placements.map(c=><li key={c.ordinal}>
            {c.source_id} · original frames {c.source_in_frame_zero}
            {' '}– {c.source_out_frame_zero} (exclusive) · at
            {' '}{filmTimeClock(c.film_start_tick)}
          </li>)}
        </ol>
        <p>Changes are not saved yet. The Windows desktop will ask for
          your approval before publishing a new immutable edit version.</p>
        <div className="actions">
          <button disabled={busy} onClick={save}>
            Save new edit revision…</button>
          <button disabled={busy} onClick={()=>{
            setDraft(null);setChange(null);
          }}>Discard proposed change</button>
        </div>
      </>}
    </>}
    {message&&<p role="alert">{message}</p>}
  </section>;
}
