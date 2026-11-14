import React,{useEffect,useRef,useState} from 'react';
import DirectorReelPlayback from './DirectorReelPlayback.jsx';
import './director-film-distribution.css';

async function api(url,method='GET',body,signal){
  const r=await fetch(url,{method,credentials:'same-origin',signal,
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!r.ok){
    const e=await r.json().catch(()=>({}));
    if(r.status===404)return null;
    throw Error(typeof e.detail==='string'?e.detail:
      'The finished movie package could not be opened.');
  }
  return r.json();
}
const ACTIVE=['queued','packing'];
export default function DirectorFilmDistribution({movie,job}){
  const root='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'');
  const base=root+'/long-film/'+encodeURIComponent(job.id);
  const [status,setStatus]=useState(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [watch,setWatch]=useState(false);
  const alive=useRef(true);
  const refresh=async()=>{
    const result=await api(base+'/package');
    if(alive.current)setStatus(result);
  };
  useEffect(()=>{
    alive.current=true;setStatus(null);setError('');setNotice('');
    setLoading(true);setWatch(false);
    refresh().catch(e=>{if(alive.current)setError(e.message)})
      .finally(()=>{if(alive.current)setLoading(false)});
    return()=>{alive.current=false};
  },[base]);
  useEffect(()=>{
    if(!status||!ACTIVE.includes(status.status))return;
    let active=true;
    const timer=setInterval(()=>{
      api(base+'/package').then(result=>{
        if(active&&alive.current)setStatus(result)
      }).catch(e=>{if(active&&alive.current)setError(e.message)});
    },1300);
    return()=>{active=false;clearInterval(timer)};
  },[base,status?.status]);

  async function act(stop=false){
    if(busy||!window.confirm(stop?
      'Stop preparing this portable film package? Your verified reels will remain safe.':
      'Prepare one portable copy of your complete verified film? This creates a separate movie package; your original Takes and finished reels are untouched.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const next=await api(base+'/package'+(stop?'/stop':''),
        'POST',{director_confirmed:true});
      if(alive.current){
        setStatus(next);setNotice(stop?
          'Stop requested. Your original film stays safe.':
          'Portable film packaging started from verified reels.');
      }
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }

  if(!job?.completed)return null;
  return <section className="director-distribution"
    aria-label="Package and watch completed movie">
    <div className="director-distribution-head">
      <div><h4>Share Your Finished Film</h4>
        <p className="film-muted">Watch the complete original-source
          finished reels, or prepare a single portable film collection
          you can save and open later in NVP.</p></div>
      <span>Checked original film reels</span>
    </div>
    {error&&<p className="director-dist-error" role="alert">{error}</p>}
    {notice&&<p className="director-dist-note" role="status">{notice}</p>}
    <div className="director-dist-actions">
      <button className="film-secondary" onClick={()=>setWatch(v=>!v)}>
        {watch?'Close Film Player':'Watch Complete Film'}
      </button>
      {!loading&&status?.status!=='completed'&&
        !ACTIVE.includes(status?.status)&&
        <button className="film-primary" disabled={busy}
          onClick={()=>act(false)}>Prepare Portable Film</button>}
      {ACTIVE.includes(status?.status)&&
        <button className="film-secondary" disabled={busy}
          onClick={()=>act(true)}>Stop Packaging</button>}
      {status?.status==='completed'&&
        <a className="film-primary" rel="noopener noreferrer"
          href={base+'/package/file'}
          download={'NVP-Film-'+job.id.slice(0,8)+'.nvpfilm'}>
          Save Portable Film (.nvpfilm)
        </a>}
    </div>
    {status&&<div className="director-dist-progress">
      {ACTIVE.includes(status.status)?<p role="status">
        Preparing portable film · {status.packed_reels} verified reels added
      </p>:status.status==='completed'?<p>
        Portable movie ready · {Math.round(status.package_bytes/1048576)} MiB
      </p>:status.issue?<p>{status.issue}</p>:null}
    </div>}
    {watch&&<DirectorReelPlayback
      sourceBase={base+'/watch'} title="Watch Your Complete Film"/>}
    <p className="film-hint">A portable NVP film contains the checked
      picture and sound reels and a source-integrity manifest. It is not
      a cinema DCP, standalone executable, or certified 4K master.
      NVP verifies its contents when you import it again.</p>
  </section>;
}
