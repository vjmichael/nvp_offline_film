import React from 'react';
import {buildDiffusionPrompt} from './diffusionPrompt.js';

/** Controlled widget for the Basic and Advanced visual-generation panels.
 * Parent must persist the selected boolean in an approved production intent,
 * never infer permission from checkbox state or send a model-selected value.
 */
export default function DirectorDiffusionMusicToggle({prompt, noBackgroundMusic, onChange, disabled=false}) {
  let compiled='', previewError='';
  try {compiled=buildDiffusionPrompt(prompt, noBackgroundMusic);}
  catch(error){previewError=error.message;}
  return <section aria-label="AI picture-generation audio guidance">
    <label>
      <input type="checkbox" checked={noBackgroundMusic} disabled={disabled}
        onChange={event=>onChange(event.target.checked)}/>
      No background music
    </label>
    <p className="film-muted">Adds a background-music restriction to the AI visual prompt.
      Original dialogue, ambience and sound effects remain under NVP control.</p>
    {previewError&&<p role="alert">{previewError}</p>}
    <label>Prepared visual-generation prompt
      <textarea readOnly value={compiled} rows={Math.min(8,compiled.split('\n').length+1)} />
    </label>
  </section>;
}
