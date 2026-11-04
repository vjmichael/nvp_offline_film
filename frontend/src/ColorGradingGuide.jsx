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
      'These parameters currently exist in a versioned backend grading recipe. Interactive color wheels, shot-local adjustments and a full grading monitor are NOT available in this UI yet.'
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
    title: '6. Future professional controls',
    summary: 'A roadmap, not a list of controls already delivered.',
    body: [
      'Grading UI: exposure and color sliders, before/after wipe, undo/redo, grade presets and a shot gallery.',
      'Advanced: lift/gamma/gain wheels, luma and hue curves, RGB parade, waveform, histogram, vectorscope, references and LUTs with declared color spaces.',
      'Professional: masks, qualifiers, motion tracking, per-shot grades, grading keyframes, HDR scopes, color-managed monitoring and independent color calibration.',
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
      <p><strong>Current status:</strong> The NVP backend has versioned grading recipes and technical mastering candidates. The full graphical grading workspace, video scopes and calibrated delivery approval are future engineering milestones.</p>
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
