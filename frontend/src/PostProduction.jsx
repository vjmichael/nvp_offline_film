import React, {useEffect,useState} from 'react';
import './index.css';
import './filmmaker-home.css';
import DirectorFilmEditor from './DirectorFilmEditor.jsx';

export default function PostProduction() {
  const query=new URLSearchParams(window.location.search);
  const id=query.get('project');
  const encrypted=query.get('encrypted')==='1';
  const [movie,setMovie]=useState(null);
  const [status,setStatus]=useState('Loading movie…');
  useEffect(()=>{
    if(!id||!/^[a-f0-9]{32}$/.test(id)) {
      setStatus('Open a movie from the NVP home first.');return;
    }
    let active=true,sequence=0;
    const deny=()=>{sequence+=1;setMovie(null);
      setStatus('This movie is locked. Unlock it from the NVP home first.');};
    const load=()=>{
      const observed=++sequence;
      fetch('/api/projects/'+id+(encrypted?'/live':''),{credentials:'same-origin'})
        .then(async response=>{
          if(!response.ok)throw new Error(response.status===423
            ? 'This movie is locked. Unlock it from the NVP home first.'
            : 'Unable to open this movie.');
          return response.json();
        })
        .then(data=>{if(active&&observed===sequence){setMovie(data);setStatus('')}})
        .catch(error=>{if(active&&observed===sequence){
          setMovie(null);setStatus(error.message);
        }});
    };
    const onStorage=event=>{
      if(event.key==='nvp-film-lock-'+id)deny();
    };
    window.addEventListener('storage',onStorage);
    window.addEventListener('focus',load);
    const check=window.setInterval(load,15000);
    load();
    return ()=>{active=false;sequence+=1;
      window.clearInterval(check);
      window.removeEventListener('storage',onStorage);
      window.removeEventListener('focus',load);
    };
  },[id,encrypted]);
  return <div className="film-post-window">
    <header className="film-topbar"><span>NVP · POST-PRODUCTION</span>
      <span>Edit Film</span></header>
    <main className="film-page">
      <div className="film-eyebrow">SEPARATE EDITING WORKSPACE</div>
      <h1>{movie?.title||'Edit your movie'}</h1>
      {status&&<p role="status">{status}</p>}
      {movie&&<>
        <DirectorFilmEditor key={movie.id+':'+movie.revision} movie={movie}/>
      </>}
      <a href="/" className="film-secondary" style={{textDecoration:'none'}}>Return to movie projects</a>
    </main>
  </div>;
}
