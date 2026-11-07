import React,{useEffect,useRef,useState} from 'react';
import './WorkspaceLock.css';

/*
 * The NVP workspace lock is an accidental-interaction guard, NOT an
 * authentication or encryption boundary. It never starts, stops, pauses or
 * cancels a production job and it never locks the operating system.
 * A separate native host command may offer an explicit OS lock later.
 */
export default function WorkspaceLock({locked,onUnlock}) {
  const [position,setPosition]=useState(0);
  const home=useRef(null);

  useEffect(()=>{
    if(locked){
      setPosition(0);
      home.current?.focus();
    }
  },[locked]);

  if(!locked)return null;

  function moveSlider(value) {
    const next=Number(value);
    if(!Number.isFinite(next))return;
    if(next>=95){
      setPosition(0);
      onUnlock();
    }else{
      setPosition(next);
    }
  }

  return <div className="nvp-lock-screen" role="dialog"
              aria-modal="true" aria-labelledby="nvp-lock-heading"
              aria-describedby="nvp-lock-description">
    <div className="nvp-lock-inner">
      <div className="nvp-lock-mark" aria-hidden="true">✦</div>
      <h1 id="nvp-lock-heading">NVP is locked</h1>
      <p id="nvp-lock-description">
        Your studio is hidden from accidental interaction.
        A production job, if running under the separate production supervisor,
        is not paused or cancelled by this screen.
      </p>
      <button className="nvp-lock-home" type="button" ref={home}
              onClick={onUnlock} aria-label="Home — open NVP">
        <span className="nvp-lock-home-icon" aria-hidden="true">⌂</span>
        Home · Open NVP
      </button>
      <div className="nvp-lock-slide">
        <label htmlFor="nvp-lock-slide-input">Or slide to open</label>
        <input id="nvp-lock-slide-input" type="range" min="0" max="100"
               step="5" value={position}
               aria-label="Slide to unlock NVP"
               onChange={event=>moveSlider(event.target.value)}/>
        <div className="nvp-lock-slide-foot" aria-hidden="true">
          <span>LOCKED</span><span>OPEN</span>
        </div>
      </div>
      <p className="nvp-lock-hint">
        This is a convenience lock, not a password or a security boundary.
        It does not lock other applications or your computer.
      </p>
    </div>
  </div>;
}
