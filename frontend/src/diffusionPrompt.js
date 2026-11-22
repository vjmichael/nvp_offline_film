// Filmmaker-facing mirror of the NVP diffusion prompt contract.
export const NO_BACKGROUND_MUSIC_LINE = 'No background music.';
export function buildDiffusionPrompt(prompt, noBackgroundMusic) {
  if(typeof prompt!=='string' || typeof noBackgroundMusic!=='boolean' ||
      !prompt.trim() || prompt.includes('\0') || prompt.includes('\r') ||
      [...prompt].some(ch=>ch.charCodeAt(0)<32 && ch!=='\n' && ch!=='\t')) {
    throw new Error('A valid prompt and explicit music option are required');
  }
  let result=prompt;
  if(noBackgroundMusic && !prompt.split('\n').some(line=>line.trim()===NO_BACKGROUND_MUSIC_LINE)) {
    result=prompt.trimEnd()+'\n'+NO_BACKGROUND_MUSIC_LINE;
  }
  if(Array.from(result).length<8 || Array.from(result).length>500)throw new Error('Prompt exceeds LTX limits');
  return result;
}
