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
