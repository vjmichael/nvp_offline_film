import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import SceneLibraryPanel from './SceneLibraryPanel.jsx';

afterEach(()=>cleanup());

const pid='a'.repeat(32),sha='b'.repeat(64);
const project={id:pid,revision:4};
const source={
  format:'nvp.plan03.scene_library.v1',
  project_id:pid,project_revision:4,scene_count:2,
  scenes:[
    {
      scene_id:'SC_kitchen',number:1,heading:'INT. KITCHEN - DAY',
      start_line:1,end_line:6,source_scene_sha256:sha,
      screenplay_text:'INT. KITCHEN - DAY\nA dog eats from a bowl.',
      screenplay_character_cues:['DOG'],
      location_from_heading:'INT. KITCHEN - DAY',
      actors:[],locations:[],props:[],props_status:'not_yet_assigned',
      stale_links:[],dialogue:[],
    },
    {
      scene_id:'SC_park',number:2,heading:'EXT. PARK - DAY',
      start_line:7,end_line:10,source_scene_sha256:'c'.repeat(64),
      screenplay_text:'EXT. PARK - DAY\nA ball rolls away.',
      screenplay_character_cues:[],
      location_from_heading:'EXT. PARK - DAY',
      actors:[],locations:[],props:[{name:'Ball',approved:true}],
      props_status:'creator_linked',stale_links:[],dialogue:[],
    }
  ],
};

describe('PLAN-03 filmmaker-first Scene Library',()=>{
  it('shows only source-grounded scenes and approved linked props',async()=>{
    const api=vi.fn(async()=>source);
    const onEdit=vi.fn(),onTool=vi.fn();
    render(<SceneLibraryPanel project={project} api={api}
      onEditScreenplay={onEdit} onOpenSceneTool={onTool}/>);
    expect(await screen.findByText('Scenes in your movie')).toBeTruthy();
    expect(screen.getByText('DOG')).toBeTruthy();
    expect(screen.getByText('Not yet assigned')).toBeTruthy();
    expect(screen.getByText(/No local model selected/)).toBeTruthy();
    expect(screen.queryByText(/Unapproved suggestions/)).toBeNull();
    fireEvent.click(screen.getByText('EXT. PARK - DAY'));
    expect(screen.getByText('Ball')).toBeTruthy();
    fireEvent.click(screen.getByText('Work on this scene'));
    expect(onTool).toHaveBeenCalledWith('stage','SC_park');
    fireEvent.click(screen.getByText('Edit screenplay'));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(api).toHaveBeenCalledWith('/projects/'+pid+'/scene-library');
  });

  it('keeps model breakdown an unapproved suggestion and never writes assets',async()=>{
    const api=vi.fn(async(path,method)=>{
      if(method==='POST')return{
        format:'nvp.plan03.ai_scene_breakdown_proposal.v1',
        status:'UNAPPROVED_PROPOSAL',creator_approval_granted:false,
        project_revision:4,scene_id:'SC_kitchen',source_scene_sha256:sha,
        suggestions:{actors:['DOG'],locations:['Kitchen'],props:['Bowl']}
      };
      return source;
    });
    render(<SceneLibraryPanel project={project} api={api}
      modelId="local-genuine-model" modelPort="1234"
      onEditScreenplay={()=>{}} onOpenSceneTool={()=>{}}/>);
    await screen.findByText('Scenes in your movie');
    fireEvent.click(screen.getByText(/Ask a local AI for scene breakdown ideas/));
    fireEvent.click(screen.getByText('Suggest actors, locations and props'));
    await screen.findByText('Unapproved suggestions — nothing has been changed');
    expect(screen.getByText('Bowl')).toBeTruthy();
    expect(api).toHaveBeenCalledWith(
      '/projects/'+pid+'/scenes/SC_kitchen/ai-breakdown',
      'POST',{model_id:'local-genuine-model',model_port:1234,expected_revision:4});
    expect(api.mock.calls.filter(x=>x[1]==='POST')).toHaveLength(1);
    fireEvent.click(screen.getByText('EXT. PARK - DAY'));
    expect(screen.queryByText('Unapproved suggestions — nothing has been changed')).toBeNull();
  });

  it('fails closed on a stale or cross-project scene library',async()=>{
    const api=vi.fn(async()=>({...source,project_id:'f'.repeat(32)}));
    render(<SceneLibraryPanel project={project} api={api}
      onEditScreenplay={()=>{}} onOpenSceneTool={()=>{}}/>);
    const alert=await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/does not match the saved screenplay revision/);
    expect(screen.queryByText('Work on this scene')).toBeNull();
  });
});
