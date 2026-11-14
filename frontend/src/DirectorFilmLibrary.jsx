import React,{useEffect,useRef,useState} from 'react';
import DirectorReelPlayback from './DirectorReelPlayback.jsx';
import './director-film-distribution.css';

async function request(url,opts={}){
  const r=await fetch(url,{credentials:'same-origin',
    headers:{'x-nvp-director':'1',...(opts.headers||{})},
    ...opts});
  if(!r.ok){
    const e=await r.json().catch(()=>({}));
    throw Error(typeof e.detail==='string'?e.detail:
      'The film collection could not be opened.');
  }
  return r.json();
}
const format=s=>{
  const n=Math.max(0,Number(s)||0);
  const h=Math.floor(n/3600),m=Math.floor(n/60)%60,x=Math.floor(n%60);
  return (h?h+':':'')+(h?String(m).padStart(2,'0'):m)+
    ':'+String(x).padStart(2,'0');
};
export default function DirectorFilmLibrary({movie}){
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/film-library';
  const [films,setFilms]=useState([]);
  const [file,setFile]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [watch,setWatch]=useState(null);
  const alive=useRef(true);
  const upload=useRef(null);
  useEffect(()=>{
    alive.current=true;setFilms([]);setWatch(null);
    setError('');setMessage('');
    if(!movie.encrypted){
      request(base).then(result=>{
        if(alive.current)setFilms(result.films||[]);
      }).catch(e=>{if(alive.current)setError(e.message)});
    }
    return()=>{alive.current=false;upload.current?.abort()};
  },[base]);
  async function refresh(){
    const result=await request(base);
    if(alive.current)setFilms(result.films||[]);
  }
  async function importFilm(e){
    e.preventDefault();
    if(!file||busy)return;
    if(!file.name.toLowerCase().endsWith('.nvpfilm')){
      setError('Choose a portable .nvpfilm movie.');return;
    }
    if(!window.confirm(
      'Import this portable film into the local Film Library? The package will be independently checked and the existing film project will remain unchanged.'))return;
    setBusy(true);setError('');setMessage(
      'Copying and checking the original film reels. Do not close this import.');
    const abort=new AbortController();upload.current=abort;
    try{
      await request(base+'/import',{
        method:'POST',body:file,signal:abort.signal,
        headers:{'Content-Type':'application/x-nvpfilm'}});
      await refresh();
      if(alive.current){
        setFile(null);
        setMessage('Your portable film has been imported and checked.');
      }
    }catch(e){
      if(alive.current)setError(e.name==='AbortError'?
        'Import cancelled; no unverified film was added.':e.message);
    }finally{
      if(alive.current)setBusy(false);
      upload.current=null;
    }
  }
  return <section className="director-film-library" aria-label="Your portable films">
    <div className="director-distribution-head">
      <div><h3>Your Film Library</h3>
        <p className="film-muted">Keep finished portable movies alongside
          your filmmaking projects. Import a complete .nvpfilm file to watch
          it here again, even after moving it between computers.</p></div>
      <span>Local originals stay separate</span>
    </div>
    {movie.encrypted?<p className="director-dist-warning">
      This movie is protected. Importing ordinary portable movies into
      encrypted film storage is paused until the protected-media library
      and encryption custody have passed acceptance.
    </p>:<>
      {error&&<p role="alert" className="director-dist-error">{error}</p>}
      {message&&<p role="status" className="director-dist-note">{message}</p>}
      <form onSubmit={importFilm} className="director-library-form">
        <label>Open a portable NVP film
          <input type="file" accept=".nvpfilm,application/x-nvpfilm"
            disabled={busy} onChange={e=>setFile(e.target.files?.[0]||null)}/>
        </label>
        <button className="film-primary" type="submit"
          disabled={!file||busy}>{busy?'Checking Film…':'Import Film'}</button>
        {busy&&<button type="button" className="film-secondary"
          onClick={()=>upload.current?.abort()}>Cancel Import</button>}
      </form>
      {!!films.length&&<div className="director-library-items">
        <h4>Saved films</h4>
        {films.map(film=><article key={film.id}>
          <div><strong>Portable film</strong>
            <p className="film-muted">{format(film.duration_seconds)}
              {' · '}{film.reels} verified reels
              {' · '}Imported {new Date(film.imported_at).toLocaleDateString()}
            </p>
          </div>
          <button className="film-secondary" onClick={()=>setWatch(
            v=>v===film.id?null:film.id)}>
            {watch===film.id?'Close Player':'Watch Film'}
          </button>
          {watch===film.id&&<DirectorReelPlayback
            sourceBase={base+'/'+film.id+'/watch'}
            title="Watch Imported Film"/>}
        </article>)}
      </div>}
      {!films.length&&!busy&&<p className="film-hint">
        Your imported films will appear here. Exported originals and
        their production histories stay in their existing film projects.</p>}
      <p className="film-hint">Import verifies the archive and each reel
        before adding it to your Library. A file hash checks integrity;
        it does not establish a trusted creator signature. No program
        code from imported films is executed.</p>
    </>}
  </section>;
}
