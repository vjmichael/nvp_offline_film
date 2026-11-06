// NVP's exact source time is an integer tick, NEVER a JS Number.
// This function is solely a human-readable view, not the authored source.
export const TICKS_PER_SECOND=7056000000n;
export function filmTimeClock(tickText){
  const tick=BigInt(tickText);
  const total=tick/TICKS_PER_SECOND;
  const millis=tick%TICKS_PER_SECOND*1000n/TICKS_PER_SECOND;
  const hours=total/3600n;
  const minutes=total/60n%60n;
  const seconds=total%60n;
  return hours.toString().padStart(2,'0')+':'+
    minutes.toString().padStart(2,'0')+':'+
    seconds.toString().padStart(2,'0')+'.'+
    millis.toString().padStart(3,'0');
}

const MAX_FILM_TICK=9223372036854775807n;

// Accept a human clock without EVER converting the authored tick into JS
// Number. Milliseconds are exactly representable in NVP's tick clock.
// Preserve sub-millisecond ticks when no clock edit is requested.
export function clockToFilmTick(clock){
  if(typeof clock!=='string' ||
     !/^[0-9]{2,6}:[0-5][0-9]:[0-5][0-9][.][0-9]{3}$/.test(clock)){
    throw new Error('Film gap must use HH:MM:SS.mmm');
  }
  const [hourText,minuteText,secondFraction]=clock.split(':');
  const [secondText,milliText]=secondFraction.split('.');
  const seconds=BigInt(hourText)*3600n+
                BigInt(minuteText)*60n+BigInt(secondText);
  const ticks=seconds*TICKS_PER_SECOND+
              BigInt(milliText)*(TICKS_PER_SECOND/1000n);
  if(ticks>MAX_FILM_TICK)
    throw new Error('Film gap exceeds the exact 64-bit duration');
  return ticks.toString();
}
