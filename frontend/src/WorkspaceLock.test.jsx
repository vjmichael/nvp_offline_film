import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import WorkspaceLock from './WorkspaceLock.jsx';

afterEach(()=>cleanup());

describe('NVP manual application lock',()=>{
  it('shows nothing while unlocked',()=>{
    const unlock=vi.fn();
    render(<WorkspaceLock locked={false} onUnlock={unlock}/>);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(unlock).not.toHaveBeenCalled();
  });

  it('hides the studio behind a modal until a deliberate Home press',()=>{
    const unlock=vi.fn();
    render(<WorkspaceLock locked={true} onUnlock={unlock}/>);
    expect(screen.getByRole('dialog',{
      name:'NVP is locked'})).toBeTruthy();
    expect(screen.getByText(/not a password or a security boundary/i))
      .toBeTruthy();
    expect(unlock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Home — open NVP'}));
    expect(unlock).toHaveBeenCalledTimes(1);
  });

  it('requires completing the slide rather than a partial movement',()=>{
    const unlock=vi.fn();
    render(<WorkspaceLock locked={true} onUnlock={unlock}/>);
    const slider=screen.getByRole('slider',{name:'Slide to unlock NVP'});
    fireEvent.change(slider,{target:{value:'40'}});
    expect(unlock).not.toHaveBeenCalled();
    fireEvent.change(slider,{target:{value:'95'}});
    expect(unlock).toHaveBeenCalledTimes(1);
  });

  it('never exposes an automatic timeout, system lock or destructive control',()=>{
    const unlock=vi.fn();
    const view=render(<WorkspaceLock locked={true} onUnlock={unlock}/>);
    expect(view.container.querySelector('input[type=password]')).toBeNull();
    expect(screen.queryByRole('button',{name:/cancel|stop|pause|lock system/i}))
      .toBeNull();
    expect(unlock).not.toHaveBeenCalled();
  });
});
