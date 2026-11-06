import React, { useState } from 'react';

/**
 * Color education is intentionally self-contained and available offline.
 * This panel is help content, NOT a claimed working grading/editor console.
 * See docs/NVP_COLOR_GRADING_BEGINNERS_GUIDE.md for the full written guide.
 */
const SECTIONS = [
  {
    title: '1. Start here: correction vs. grading',
    summary: 'Learn the difference between making a shot accurate and making it expressive.',
    body: [
      'Color correction fixes the technical baseline: white balance, unwanted color casts, exposure and shot-to-shot consistency.',
      'Color grading gives the story a visual mood. Warm colors may suggest comfort; cool or desaturated colors can suggest distance, uncertainty or nighttime.',
      'A grade should be reversible. NVP keeps the original Digital Take and scene-linear OpenEXR source unchanged.'
    ]
  },
  {
    title: '2. The first six controls',
    summary: 'The COLOR-01B2 engine currently supports a global grade recipe with these settings.',
    body: [
      'Exposure (stops): +1 doubles the scene-linear intensity before ACES tone mapping. Start with small increments such as ±0.25.',
      'Contrast: expands or compresses the distance between dark and bright tones. Do not crush shadows for a “cinematic” look by default.',
      'Saturation: controls color intensity; 0 removes color, 1 is neutral, and values above 1 make colors more vivid.',
      'Red, green and blue gains: shift the linear balance to create a warmer or cooler tone. These are creative RGB gains, not a calibrated Kelvin white-balance instrument.',
      'The Essentials grading workspace now offers sliders and numeric controls, presets, undo/redo, a real OCIO preview and versioned draft saves. Calibrated monitors, professional wheels and shot-local adjustments remain future work.'
    ]
  },
  {
    title: '3. The correct order of operations',
    summary: 'A repeatable production workflow helps make the colors look right everywhere.',
    body: [
      'First, preserve the frozen take and verify that the images truly are scene-linear HALF OpenEXRs.',
      'Next, declare and verify the source primaries. Exposure, contrast, saturation and balance adjustments occur before the output display transform.',
      'Then, apply the pinned ACES 2 / OpenColorIO output view. COLOR-01B2 uses a Rec.1886/Rec.709 SDR viewing target, not a random gamma filter.',
      'Finally, transform into BT.709-matrix limited-range 10-bit 4:2:2 video, check the tags, fully decode the result, and compare it to the graded source reference.',
      'A successful encode is a technical candidate, not creative approval, a calibrated display, or a certified cinema master.'
    ]
  },
  {
    title: '4. The formats explained',
    summary: 'OpenEXR, ACES 2, ProRes, DNxHR and DCP solve different problems.',
    body: [
      'OpenEXR HALF stores high-precision scene-linear image values, including highlights above 1.0. Encoding an 8-bit PNG in a 10-bit MOV does not recreate those values.',
      'OpenColorIO/ACES 2 defines and applies the color/view transform. Color-space tags are metadata: they cannot replace an actual transform.',
      'ProRes 422 HQ and DNxHR HQX are editing-friendly, lossy 10-bit 4:2:2 MOV formats. Their decoded pixels may differ slightly from the original graded image.',
      'DCP is a separate theatrical presentation format, including JPEG 2000/MXF, sound, package XML, cinema XYZ and projection-ingest checks.'
    ]
  },
  {
    title: '5. A five-minute practice session',
    summary: 'Learn each adjustment before combining them.',
    body: [
      'Start neutral. Try +0.25 stop exposure and compare before/after. Reset to neutral.',
      'Reduce saturation to 0.7, then to 0.0 to see the difference between muted and grayscale. Reset.',
      'Try a slight warm look: red gain 1.03 and blue gain 0.97; compare against the original image. Reset.',
      'Try contrast 1.08. Watch both bright detail and black levels rather than just the middle of the picture.',
      'Save the look as a separate version. Never overwrite the frozen source. Technical builds require a fresh output ID for new mastering candidates.'
    ]
  },
  {
    title: '6. Grade one shot at a time, and read the scopes',
    summary: 'What lift, gamma, gain, histogram, waveform and vectorscope actually tell you.',
    body: [
      'Choose a shot card below the Essentials controls. Its frozen frame boundaries come from the original Digital Take; each shot has its own lift, gamma and gain values. The overall Essentials grade still affects every shot.',
      'Lift gently adjusts dark tonal values; gamma changes the middle tones around the scene-linear gray pivot; gain scales RGB values, often affecting bright color balance. Neutral settings are lift 0, gamma 1, gain 1.',
      'Use the histogram to see pixel counts across dark and bright levels; the waveform to see where brightness appears across the picture; the vectorscope to see chroma direction and saturation.',
      'The scopes are measured from the same post-ACES 16-bit RGB values as the actual preview, rather than browser CSS. They are software instruments, not a calibrated grading monitor.',
      'Save advanced draft looks with a separate look ID and explicit source-primaries declaration. Saved versions are reversible and do not export a final master.'
    ]
  },
  {
    title: '7. Tone curves and reference-shot advice',
    summary: 'Understand HDR exposure curves and why NVP never applies shot matching behind your back.',
    body: [
      'Under the Shot grading panel, NVP has a real scene-linear tone curve. Deep black and bright white are fixed; shadows, middle gray, and highlights can be raised or lowered in exposure stops.',
      'The original Cycles HALF OpenEXR values remain untouched. Curve offsets are applied before the pinned ACES output view, preserving legitimate HDR source radiance rather than operating on 8-bit movie previews.',
      'Choose a reference frame from another shot and request Compare reference. NVP measures real decoded pixel luminance and reports a bounded exposure proposal. This is a heuristic, not a calibrated or automatic color match.',
      'The separate Apply suggestion button adjusts the current shot only after you choose it. Undo/redo/reset are available, and saved curve looks become immutable unapproved FilmIndex draft versions.',
      'LUT import is a following stage because a LUT must specify its expected source and destination color spaces and be independently validated.'
    ]
  },
  {
    title: '8. Future professional controls',
    summary: 'A roadmap, not a list of controls already delivered.',
    body: [
      'Available in Essentials: exposure and RGB controls, before/after wipe, undo/redo, global look presets and versioned draft saves. A per-shot gallery remains future work.',
      'Still planned: graphical trackball wheels, luma and hue curves, detailed RGB parade, color-reference matching and validated LUTs with declared color spaces.',
      'Professional work still planned: masks, qualifiers, motion tracking, per-frame grading keyframes, HDR scopes, calibrated monitoring and independently verified color targets.',
      'AI can propose a look or assist with shot matching, but the filmmaker approves and can always revert its edits.'
    ]
  }
];

export default function ColorGradingGuide() {
  const [expanded, setExpanded] = useState(0);
  return (
    <main className="card" aria-labelledby="nvp-color-guide-title" style={{ maxWidth: 1000, margin: '1rem auto', padding: '1.5rem' }}>
      <div className="kicker">NVP LEARNING CENTER</div>
      <h2 id="nvp-color-guide-title">Color grading — start with the story</h2>
      <p>Color correction makes images technically consistent. Color grading shapes the visual feeling of your film. You can learn both without sacrificing the original Digital Take.</p>
      <p><strong>Current status:</strong> Essentials includes real EXR previews and global draft looks. The advanced section includes per-shot lift/gamma/gain and measured histogram, waveform and vectorscope. A further section now provides HDR EV tone curves and source-derived reference-shot exposure advice. Calibrated monitors, curves, masks and final grading approval remain future work.</p>
      <div aria-label="Color grading topics">
        {SECTIONS.map((section, index) => (
          <section key={section.title} style={{ margin: '0.75rem 0', borderTop: '1px solid var(--border, #444)', paddingTop: '0.75rem' }}>
            <h3 style={{ margin: '0 0 0.35rem' }}>
              <button type="button" aria-expanded={expanded === index}
                onClick={() => setExpanded(expanded === index ? -1 : index)}
                style={{ cursor: 'pointer', background: 'transparent', color: 'inherit', border: 0, padding: '0.25rem 0', fontSize: 'inherit', textAlign: 'left' }}>
                {expanded === index ? '▾' : '▸'} {section.title}
              </button>
            </h3>
            <p style={{ margin: '0.3rem 0' }}>{section.summary}</p>
            {expanded === index &&
              <ul style={{ paddingLeft: '1.4rem', lineHeight: 1.65 }}>
                {section.body.map((paragraph) => <li key={paragraph} style={{ margin: '0.6rem 0' }}>{paragraph}</li>)}
              </ul>}
          </section>
        ))}
      </div>
      <p><strong>Mastering safety checklist:</strong> original take frozen · genuine EXR source verified · source primaries declared · ACES transform pinned · clipping measured · complete 24fps frames · MOV codec and color tags checked · 10-bit legal range and decoded picture verified · grade approved separately.</p>
      <p>This help is available offline in NVP. More detail: <code>docs/NVP_COLOR_GRADING_BEGINNERS_GUIDE.md</code>.</p>
    </main>
  );
}
