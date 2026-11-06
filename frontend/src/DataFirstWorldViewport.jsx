import React from 'react';

// DATA-AV-01: interactive WORLD-STATE PROJECTION, not an output movie.
// Object positions are sampled from the immutable OpenUSD scene at the
// actual audio device's Film Time. This simple schematic intentionally
// does not claim full geometry/lighting/photoreal presentation acceptance.
function iso(v){
  const [x,y,z]=v;
  return [300+(x-y)*16,146+(x+y)*7-z*17];
}

export default function DataFirstWorldViewport({objects=[],listenerPath='',tick='0'}){
  const bounded=Array.isArray(objects)?objects.slice(0,64):[];
  const lines=[];
  for(let k=-10;k<=10;k+=5){
    lines.push([[k,-10,0],[k,10,0]]);
    lines.push([[-10,k,0],[10,k,0]]);
  }
  return <section aria-label="Live 3D source world-state view">
    <p className="fineprint">Scene world-state at {tick} exact Film Time ticks.
      Locations come from the recorded OpenUSD scene, not a movie stream.</p>
    <svg viewBox="0 0 600 290" width="100%" role="img"
      aria-label="Isometric source world positions and virtual listener"
      style={{maxHeight:'290px',background:'rgba(100,110,130,0.07)',
              borderRadius:'8px'}}>
      {lines.map((segment,i)=>{
        const [a,b]=segment.map(iso);
        return <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]}
          stroke="currentColor" strokeOpacity=".13"/>;
      })}
      {bounded.map((obj)=>{
        const where=obj?.world_translation;
        if(!Array.isArray(where)||where.length!==3||
           where.some(x=>typeof x!=='number'||!Number.isFinite(x)))return null;
        const [x,y]=iso(where);
        const current=obj.path===listenerPath;
        return <g key={obj.path} data-usd-path={obj.path}>
          <circle cx={x} cy={y} r={current?9:6}
            fill={current?'#10b981':obj.semantic_role==='actor'
              ?'#a855f7':'#64748b'} stroke="currentColor"
            strokeWidth={current?1.5:0.6}/>
          <text x={x+12} y={y-6} fontSize="10"
            fill="currentColor">{obj.path.split('/').at(-1)}</text>
          {current&&<circle cx={x} cy={y} r="15"
            fill="none" stroke="#10b981" strokeDasharray="3 3"/>}
        </g>;
      })}
    </svg>
    <p className="fineprint">Green marker: audition listener.
      Purple: scene actor. Grey: other scene object. This view does
      not substitute for real interactive 3D geometry and lighting.</p>
  </section>;
}
