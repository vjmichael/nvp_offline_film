import React,{useMemo,useRef,useState} from 'react';

/** CAM-FX-03: actual source-coordinate 3D point/target/tangent gizmo.
 *
 * An orbitable orthographic 3D projection is used ONLY for editing the
 * native metre-valued typed path. Actor boxes and targets originate from
 * a host-reopened actual OpenUSD 01E world source receipt. All edits still
 * pass the host's original-camera native validation before publication.
 * This is not a rendered Cycles picture, a Unity-style 3D physics gizmo,
 * or an artist-approved occlusion determination.
 */
const WIDTH=780,HEIGHT=430;
const MAX_WORLD=100000,MAX_SPEED=250;
const DOT=(a,b)=>a.reduce((sum,v,i)=>sum+v*b[i],0);
const ADD=(a,b)=>a.map((v,i)=>v+b[i]);
const SUB=(a,b)=>a.map((v,i)=>v-b[i]);
const SCALE=(a,s)=>a.map(v=>v*s);
const UNIT=(n,min,max)=>Math.min(max,Math.max(min,n));
const ROUND=x=>Number(x.toFixed(4));
const BOX_LINES=[
  [0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],
  [3,7],[4,5],[4,6],[5,7],[6,7]
];

function corners(box){
  if(!Array.isArray(box)||box.length!==2)return [];
  return [0,1].flatMap(i=>[0,1].flatMap(j=>[0,1].map(k=>[
    box[i][0],box[j][1],box[k][2]])));
}
function bases(yaw,elevation){
  const angle=yaw*Math.PI/180,alt=elevation*Math.PI/180;
  const horizontal=[Math.cos(angle),Math.sin(angle),0];
  const depth=[-Math.sin(angle),Math.cos(angle),0];
  const up=[-Math.sin(alt)*depth[0],-Math.sin(alt)*depth[1],
            Math.cos(alt)];
  return {right:horizontal,up};
}
function centerOfScene(nodes,origin,actors){
  const list=[
    ...nodes.map(n=>ADD(n.position_m,origin)),
    ...actors.map(a=>a.center_world_m)
  ];
  if(!list.length)return origin;
  return [0,1,2].map(i=>list.reduce((acc,p)=>acc+p[i],0)/list.length);
}
function project(point,center,basis,zoom){
  const delta=SUB(point,center);
  return [WIDTH/2+DOT(delta,basis.right)*zoom,
          HEIGHT/2-DOT(delta,basis.up)*zoom];
}
/** Inverse horizontal plane at original handle height (no arbitrary Z leap). */
function planarDelta(dx,dy,basis,zoom){
  const right=basis.right,up=basis.up;
  const s=dx/zoom,v=-dy/zoom;
  const det=right[0]*up[1]-right[1]*up[0];
  if(Math.abs(det)<.1)throw Error('Tilt rail view to edit in XY');
  return [(s*up[1]-right[1]*v)/det,
          (right[0]*v-s*up[0])/det];
}

export default function CameraRailGizmo({
  nodes,origin,onNodesChange,guidance,disabled=false
}){
  const [yaw,setYaw]=useState(35);
  const [elevation,setElevation]=useState(45);
  const [zoom,setZoom]=useState(13);
  const [selected,setSelected]=useState(0);
  const [notice,setNotice]=useState('');
  const gesture=useRef(null);
  const actors=guidance?.source_guided_frames?.[0]?.original_actor_views||[];
  const center=useMemo(()=>centerOfScene(nodes,origin,actors),
    [nodes,origin,actors]);
  const basis=useMemo(()=>bases(yaw,elevation),[yaw,elevation]);
  const xy=point=>project(point,center,basis,zoom);
  const localToWorld=node=>ADD(node.position_m,origin);
  const safeEdit=(index,field,position)=>{
    if(disabled||!nodes[index])return;
    if(position.some(v=>!Number.isFinite(v)||Math.abs(v)>MAX_WORLD)){
      setNotice('Camera handle exceeds original film source coordinate limits');
      return;
    }
    const edited=nodes.map((node,i)=>i===index?{
      ...node,[field]:position.map(ROUND)}:node);
    onNodesChange(edited);
    setNotice('Unapproved source-coordinate rail handle edited; revalidate before OS publish');
  };
  const beginDrag=(e,index,kind)=>{
    if(disabled||!nodes[index])return;
    e.preventDefault();e.stopPropagation();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setSelected(index);
    gesture.current={
      index,kind,clientX:e.clientX,clientY:e.clientY,
      node:structuredClone(nodes[index]),
      pointerId:e.pointerId};
  };
  const pointerMove=e=>{
    if(!gesture.current||disabled)return;
    const g=gesture.current;
    if(e.pointerId!==g.pointerId)return;
    const bounds=e.currentTarget.getBoundingClientRect();
    const dx=(e.clientX-g.clientX)*WIDTH/Math.max(1,bounds.width);
    const dy=(e.clientY-g.clientY)*HEIGHT/Math.max(1,bounds.height);
    const delta=planarDelta(dx,dy,basis,zoom);
    if(g.kind==='position'||g.kind==='target'){
      const field=g.kind==='position'?'position_m':'target_m';
      safeEdit(g.index,field,[
        g.node[field][0]+delta[0],
        g.node[field][1]+delta[1],
        g.node[field][2]]);
    }else{
      const field=g.kind==='tangent_in'?
        'tangent_in_mps':'tangent_out_mps';
      const tangent=[g.node[field][0]+delta[0]*2,
        g.node[field][1]+delta[1]*2,g.node[field][2]];
      const length=Math.hypot(...tangent);
      safeEdit(g.index,field,
        length>MAX_SPEED?SCALE(tangent,MAX_SPEED/length):tangent);
    }
  };
  const stopDrag=()=>{gesture.current=null;};
  const keyboard=(e,index,kind)=>{
    if(disabled)return;
    const step=e.shiftKey?.1:.25;
    const movement={
      ArrowLeft:[-step,0,0],ArrowRight:[step,0,0],
      ArrowUp:[0,step,0],ArrowDown:[0,-step,0],
      PageUp:[0,0,step],PageDown:[0,0,-step]}[e.key];
    if(!movement)return;
    e.preventDefault();
    setSelected(index);
    const field=kind==='target'?'target_m':'position_m';
    safeEdit(index,field,ADD(nodes[index][field],movement));
  };
  const drawLine=(p,q,id,dash=false)=>(
    <line key={id} x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]}
      stroke="currentColor" opacity={.55}
      strokeWidth={dash?1:1.4}
      strokeDasharray={dash?'4 4':undefined}/>);
  const start=xy(center);
  return <section aria-label="Interactive native-source 3D camera rail gizmo">
    <h5>3D director rail editor · original scene coordinates</h5>
    <p className="fineprint">Drag numbered camera handles, crosshair
      target handles or tangent grips. Arrow keys move the selected
      handle in X/Y; Page Up/Down adjusts its height in metres.
      Mouse orbit controls change the view only, not actor geometry.
      Numeric source validation remains mandatory before saving.</p>
    <div className="actions">
      <label>Orbit horizontal °
        <input type="range" min={-180} max={180} step={5}
          aria-label="3D rail orbit yaw" value={yaw}
          onChange={e=>setYaw(Number(e.target.value))}/></label>
      <label>Orbit elevation °
        <input type="range" min={15} max={80} step={5}
          aria-label="3D rail orbit elevation" value={elevation}
          onChange={e=>setElevation(Number(e.target.value))}/></label>
      <label>3D zoom
        <input type="range" min={3} max={65} step={1}
          aria-label="3D rail scene zoom" value={zoom}
          onChange={e=>setZoom(Number(e.target.value))}/></label>
    </div>
    <svg viewBox={'0 0 '+WIDTH+' '+HEIGHT} role="img"
      aria-label="Editable 3D projected original camera rail and source ActorID bounds"
      style={{width:'100%',maxWidth:780,height:'auto',aspectRatio:'780 / 430',
        background:'#172536',border:'1px solid #6b8095',borderRadius:9,
        touchAction:'none',color:'#99afc7'}}
      onPointerMove={pointerMove} onPointerUp={stopDrag}
      onPointerCancel={stopDrag} onLostPointerCapture={stopDrag}>
      <g opacity={.23}>
        {Array.from({length:19},(_,i)=>{
          const k=i-9;
          return <React.Fragment key={i}>
            {drawLine(xy(ADD(center,[-9,k,0])),
              xy(ADD(center,[9,k,0])),'grid-x-'+i)}
            {drawLine(xy(ADD(center,[k,-9,0])),
              xy(ADD(center,[k,9,0])),'grid-y-'+i)}
          </React.Fragment>;
        })}
      </g>
      <g strokeWidth={3}>
        <line x1={start[0]} y1={start[1]}
          x2={xy(ADD(center,[3,0,0]))[0]}
          y2={xy(ADD(center,[3,0,0]))[1]} stroke="#fa9879"/>
        <line x1={start[0]} y1={start[1]}
          x2={xy(ADD(center,[0,3,0]))[0]}
          y2={xy(ADD(center,[0,3,0]))[1]} stroke="#6bd4a3"/>
        <line x1={start[0]} y1={start[1]}
          x2={xy(ADD(center,[0,0,3]))[0]}
          y2={xy(ADD(center,[0,0,3]))[1]} stroke="#74bcff"/>
      </g>
      <g aria-label="Actual source ActorID geometry bounds">
        {actors.slice(0,24).map((actor,i)=>{
          const pts=corners(actor.bounds_world_m).map(xy);
          const at=xy(actor.center_world_m);
          return <g key={actor.actor_id}>
            {pts.length===8&&BOX_LINES.map(([a,b],j)=>
              <line key={j} x1={pts[a][0]} y1={pts[a][1]}
                x2={pts[b][0]} y2={pts[b][1]}
                stroke="#f9ce8b" opacity={.68} strokeWidth={1.2}/>)}
            <circle cx={at[0]} cy={at[1]} r={4}
              fill="#f9ce8b"/>
            <text x={at[0]+8} y={at[1]-9}
              fontSize={12} fill="#f9ce8b">ActorID {actor.actor_id.slice(0,23)}</text>
          </g>;
        })}
      </g>
      <polyline fill="none" stroke="#70d7e0" strokeWidth={2.5}
        points={nodes.map(n=>xy(localToWorld(n)).join(',')).join(' ')}/>
      {nodes.map((node,i)=>{
        const p=xy(localToWorld(node));
        const target=xy(ADD(node.target_m,origin));
        const next=nodes[i+1];
        const left=xy(ADD(localToWorld(node),SCALE(node.tangent_in_mps,.5)));
        const right=xy(ADD(localToWorld(node),SCALE(node.tangent_out_mps,.5)));
        return <g key={i}>
          {drawLine(p,target,'target-line-'+i,true)}
          {drawLine(left,right,'tangent-line-'+i)}
          {drawLine(p,xy([localToWorld(node)[0],
            localToWorld(node)[1],center[2]]),'altitude-'+i,true)}
          <circle cx={p[0]} cy={p[1]} r={selected===i?10:8}
            fill={selected===i?'#29d5cb':'#77b5ff'} stroke="#fff"
            strokeWidth={2} role="button" tabIndex={0}
            aria-label={'3D drag camera handle '+(i+1)}
            onPointerDown={e=>beginDrag(e,i,'position')}
            onKeyDown={e=>keyboard(e,i,'position')}/>
          <text x={p[0]+12} y={p[1]-12}
            fontSize={13} fill="#fff">C{i+1}</text>
          <circle cx={target[0]} cy={target[1]} r={6}
            fill="#ffe4a1" stroke="#e29e39" strokeWidth={2}
            role="button" tabIndex={0}
            aria-label={'3D drag look-at target '+(i+1)}
            onPointerDown={e=>beginDrag(e,i,'target')}
            onKeyDown={e=>keyboard(e,i,'target')}/>
          <circle cx={left[0]} cy={left[1]} r={4}
            fill="#f9ac80" role="button" tabIndex={0}
            aria-label={'3D drag incoming tangent '+(i+1)}
            onPointerDown={e=>beginDrag(e,i,'tangent_in')}/>
          <circle cx={right[0]} cy={right[1]} r={4}
            fill="#f9ac80" role="button" tabIndex={0}
            aria-label={'3D drag outgoing tangent '+(i+1)}
            onPointerDown={e=>beginDrag(e,i,'tangent_out')}/>
          {next&&drawLine(p,xy(localToWorld(next)),'rail-step-'+i)}
        </g>;
      })}
      <text x={12} y={23} fontSize={12} fill="#dfe5ed">
        Genuine source metres · Z up · 3D orbit {yaw}° / {elevation}°
      </text>
      <text x={12} y={HEIGHT-13} fontSize={12} fill="#dfe5ed">
        Cyan: path · Gold: source ActorID bounds · Orange: tangents
      </text>
    </svg>
    {nodes.length>0&&<p role="status">Selected source handle:
      {' '+(Math.min(selected,nodes.length-1)+1)}.
      Position {nodes[Math.min(selected,nodes.length-1)].position_m.join(', ')} m.
      Original Film Time tick {
        nodes[Math.min(selected,nodes.length-1)].tick}.</p>}
    {notice&&<p role="status">{notice}</p>}
    <p className="fineprint">ActorID bounds appear only after the installed host
      returns verified native USD source guidance. Without such a receipt,
      the gizmo displays the rail handles alone, not invented actors.</p>
  </section>;
}
