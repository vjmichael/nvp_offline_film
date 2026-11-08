// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Film03ActorBiblePanel from './Film03ActorBiblePanel.jsx';
import Film03ScriptChangeImpactPanel from './Film03ScriptChangeImpactPanel.jsx';

const pid='a'.repeat(32);
const actorId='b'.repeat(32);
const assetSha='c'.repeat(64);
const project={id:pid,revision:2,scenes:[{id:'SC_A',heading:'INT. RELAY - NIGHT'}]};
const actor={id:actorId,actor_id:actorId,kind:'character',name:'DONUT',revision:3,
  aliases:[],facts:[],scene_links:[]};
const links={format:'nvp.film03.production_bible_actor_links.v1',project_id:pid,
  actor_id:actorId,actor_name:'DONUT',bible_revision:3,active_links:[],history:[]};
const catalog={format:links.format,project_id:pid,
  sources:[{family:'screenplay_scene',target_id:'SC_A',target_revision:2,
            kind:'scene',name:'INT. RELAY - NIGHT'},
           {family:'filmindex',target_id:'DonutAsset',target_revision:1,
            kind:'asset',sha256:assetSha}],supported_roles:['scene','model']};

describe('FILM03-02 director ActorID and screenplay impact UI',()=>{
  afterEach(()=>{cleanup();vi.restoreAllMocks();});

  it('shows stable Bible ActorID and writes explicit versioned source links only on director click',async()=>{
    const refreshBible=vi.fn(async()=>{});
    const calls=[];
    const api=vi.fn(async(url,method,body)=>{
      calls.push({url,method,body});
      if(url.endsWith('/actor-catalog')) return catalog;
      if(url.endsWith('/voice-candidates')) return {
        format:'nvp.film03.voice_candidate_audition_catalog.v1',
        project_id:pid,actor_id:actorId,candidates:[],
        no_automatic_voice_approval:true,
      };
      if(url.endsWith('/asset-audit')) return {
        format:'nvp.film03.actor_asset_source_audit.v1',
        actor_id:actorId,all_current_sources_physically_verified:false,
        links:[],source_failures:[],
        director_review_required:[{role:'voice',reason:'No current approved VoiceID'}],
        current_voice_id:null,no_assets_or_takes_modified:true,
      };
      if(url.endsWith('/actors/'+actorId))return links;
      if(url.endsWith('/actors/'+actorId+'/links')&&method==='POST')
        return {...links,bible_revision:4,active_links:[{
          link_id:'d'.repeat(32),link_revision:1,role:body.role,
          source_family:body.source_family,target_id:body.target_id,
          target_revision:body.target_revision,production_scope:body.production_scope,
          source_sha256:assetSha,actor_prim_path:null,director_note:body.director_note,
        }],history:[]};
      throw new Error('Unreviewed API '+url);
    });
    render(<Film03ActorBiblePanel project={project} actor={actor} api={api}
      action={async fn=>fn()} busy={false} refreshBible={refreshBible}/>);
    await waitFor(()=>expect(screen.getAllByText(actorId).length).toBeGreaterThan(0));
    expect(api.mock.calls.every(([,method])=>!method||method==='GET')).toBe(true);
    fireEvent.change(screen.getByLabelText('Actor resource role'),
      {target:{value:'model'}});
    await waitFor(()=>expect(screen.getByLabelText('Actor source resource').value)
      .toContain('DonutAsset'));
    fireEvent.click(screen.getByRole('button',{name:'Link verified source'}));
    await waitFor(()=>expect(calls.some(x=>x.method==='POST')).toBe(true));
    const wrote=calls.find(x=>x.method==='POST');
    expect(wrote.body.expected_actor_revision).toBe(3);
    expect(wrote.body.role).toBe('model');
    expect(wrote.body.target_id).toBe('DonutAsset');
    expect(wrote.body.target_revision).toBe(1);
    expect(wrote.body.link_id).toBe(null);
    expect(refreshBible).toHaveBeenCalledWith(pid);
    expect(await screen.findByText(/Linked at a new durable production-bible revision/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{
      name:'Verify all source assets linked to this ActorID'}));
    expect(await screen.findByText(/Asset\/source review required/)).toBeTruthy();
    expect(screen.getByText(/No current approved VoiceID/)).toBeTruthy();
    expect(calls.filter(x=>x.method==='POST')).toHaveLength(1);
  });

  it('requires actual trusted desktop host confirmation for immutable script source capture',async()=>{
    const original=window.pywebview;
    const oldConfirm=window.confirm;
    try{
      window.confirm=vi.fn(()=>true);
      const native=vi.fn(async request=>({
        format:'nvp.film03.native_director_script_snapshot_result.v1',
        project_id:request.project_id,object_id:request.script_id,
        revision:1,host_native_director_confirmation:true,
        original_spoken_voice_mutated:false,
        original_visual_take_mutated:false,
        film_or_native_worker_execution_authorized:false,
      }));
      window.pywebview={api:{film03_publish_script_snapshot:native}};
      let captured=false;
      const api=vi.fn(async(url,method)=>{
        expect(method===undefined||method==='GET').toBe(true);
        if(url.endsWith('/script-sources'))return {
          sources:captured?[{script_id:'NvpFilm03MainDialogue',revision:1,
                             screenplay_revision:2,source_sha256:'f'.repeat(64)}]:[]};
        throw new Error('Unexpected HTTP write or unknown route '+url);
      });
      native.mockImplementationOnce(async request=>{
        captured=true;
        return {
          format:'nvp.film03.native_director_script_snapshot_result.v1',
          project_id:request.project_id,object_id:request.script_id,
          revision:1,host_native_director_confirmation:true,
          original_spoken_voice_mutated:false,
          original_visual_take_mutated:false,
          film_or_native_worker_execution_authorized:false,
        };
      });
      render(<Film03ScriptChangeImpactPanel
        project={{...project,screenplay:'INT. RELAY - NIGHT\n\nDONUT\nI hear the relay.'}} api={api}/>);
      const button=await screen.findByRole('button',{name:/Capture script revision/});
      expect(button.disabled).toBe(false);
      fireEvent.click(button);
      await waitFor(()=>expect(native).toHaveBeenCalledTimes(1));
      expect(native.mock.calls[0][0]).toEqual({
        project_id:pid,script_id:'NvpFilm03MainDialogue',
        expected_screenplay_revision:2,expected_manifest_revision:0});
      expect(await screen.findByText(/captured under desktop director confirmation/)).toBeTruthy();
      expect(api.mock.calls.every(([,method])=>!method||method==='GET')).toBe(true);
    }finally{
      window.pywebview=original;
      window.confirm=oldConfirm;
    }
  });

  it('shows existing dialogue impact but never grants editor approval or silently rerecords',async()=>{
    const api=vi.fn(async(url,method)=>{
      if(url.endsWith('/script-sources'))return {sources:[
        {script_id:'Relay03Script',revision:2,screenplay_revision:1,
         source_sha256:'e'.repeat(64)}]};
      if(url.endsWith('/script-impact/Relay03Script'))return {
        format:'nvp.film03.readonly_script_dialogue_impact.v1',
        screenplay_revision:2,last_published_script_snapshot_revision:2,
        new_or_changed_script_lines:[{
          scene_id:'SC_A',line_id:'Dlg_Original',speaker:'DONUT',kind:'revised',
          old_text:'The relay has been silent.',new_text:'The relay is back.'
        }],impacted_historical_performances:[{
          performance_id:'DonutOldLine',old_script_revision:1,
          current_text:'The relay is back.'
        }],previous_revision_indexed_production_dependents:[],
        production_bible:{issues:[{entity_id:actorId,entity_name:'DONUT',
          scene_id:'SC_A',type:'scene_changed'}]},
        requires_manual_lineage_review:false,
        retakes_performed_automatically:false,old_audio_takes_modified:false,
      };
      throw new Error('Unexpected '+url);
    });
    render(<Film03ScriptChangeImpactPanel project={project} api={api}/>);
    const button=await screen.findByRole('button',{name:/Review source impacts/});
    fireEvent.click(button);
    expect(await screen.findByText(/Previous: The relay has been silent/)).toBeTruthy();
    expect(screen.getByText(/Current: The relay is back/)).toBeTruthy();
    expect(screen.getByText(/Historical performance: DonutOldLine/)).toBeTruthy();
    expect(screen.getByText(/scene_changed/)).toBeTruthy();
    expect(api.mock.calls.every(([,method])=>!method||method==='GET')).toBe(true);
  });
});
