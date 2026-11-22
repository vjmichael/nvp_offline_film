import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import FeatureExportDetails from './FeatureExportDetails.jsx';

describe('bounded export evidence',()=>{
  const features=[{feature_id:'job',assembly_id:'Opening',state:'REVIEW_REQUIRED'}];
  it('loads only on open and pages without exposing worker controls',async()=>{
    const api={wo5_review_feature_page:vi.fn(async (project_id,feature_id,first,kind)=>({project_id,feature_id,first,kind,state:'REVIEW_REQUIRED',total:33,next_first:first===0?32:null,entries:[{reel:first+1,frames:7200,picture_sha256:'a'.repeat(64),sound_sha256:'b'.repeat(64)}]}))};
    const {container}=render(<FeatureExportDetails projectId="movie" features={features} api={api}/>);
    expect(api.wo5_review_feature_page).not.toHaveBeenCalled();
    const details=container.querySelector('details');details.open=true;fireEvent(details,new Event('toggle'));
    expect(await screen.findByText('Reel 1 · 7200 frames')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Next'}));
    expect(await screen.findByText('Reel 33 · 7200 frames')).toBeTruthy();
    expect(api.wo5_review_feature_page).toHaveBeenLastCalledWith('movie','job',32,'source');
    expect(screen.getByRole('button',{name:'Next'}).disabled).toBe(true);
    expect(screen.queryByRole('button',{name:/retry export|approve|cancel/i})).toBeNull();
  });
  it('rejects foreign results with a concise message',async()=>{
    const api={wo5_review_feature_page:vi.fn(async()=>({project_id:'other'}))};
    const {container}=render(<FeatureExportDetails projectId="movie" features={features} api={api}/>);
    const details=container.querySelector('details');details.open=true;fireEvent(details,new Event('toggle'));
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('unavailable'));
  });
});
