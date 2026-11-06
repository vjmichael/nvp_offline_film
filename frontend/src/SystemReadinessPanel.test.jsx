import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SystemReadinessPanel from './SystemReadinessPanel.jsx';

const snapshot={
  format:'nvp.system_ready.native_packages.v1',status:'ACTION_NEEDED',
  auto_install:false,os_authorization_required:true,
  components:[
    {id:'video_tools',name:'FFmpeg and FFprobe',status:'ready',
     supplied_by:'NVP installer',required:true,repair:null},
    {id:'desktop_shell',name:'Linux GTK/WebKit',status:'missing',
     supplied_by:'not found',required:true,repair:'linux_webkit'},
    {id:'disk_cache',name:'Temporary picture/sound review disk space',
     status:'ready',free_mb:5800,required:true,
     supplied_by:'local disk',repair:null},
  ],
};
describe('NVP system package discovery and physical consent UX',()=>{
  it('reads missing packages without installing anything on startup',async()=>{
    const native={
      system_package_inventory:vi.fn(async()=>snapshot),
      repair_system_package:vi.fn(),
    };
    render(<SystemReadinessPanel nativeBridge={native}/>);
    expect(await screen.findByText('Linux GTK/WebKit')).toBeTruthy();
    expect(screen.getByText('FFmpeg and FFprobe')).toBeTruthy();
    expect(screen.getByText(/Provided by: NVP installer/)).toBeTruthy();
    expect(native.repair_system_package).not.toHaveBeenCalled();
    expect(screen.getByText('Ask to install Linux GTK/WebKit')).toBeTruthy();
  });

  it('requests only a fixed component ID when creator chooses install',async()=>{
    const native={
      system_package_inventory:vi.fn(async()=>snapshot),
      repair_system_package:vi.fn(async component=>({
        format:'nvp.system_ready.native_packages.v1',
        status:'DECLINED',component,source_media_modified:false,
      })),
    };
    render(<SystemReadinessPanel nativeBridge={native}/>);
    fireEvent.click(await screen.findByText('Ask to install Linux GTK/WebKit'));
    await waitFor(()=>expect(native.repair_system_package)
      .toHaveBeenCalledWith('linux_webkit'));
    expect(await screen.findByText(/Installation was cancelled/)).toBeTruthy();
    expect(native.repair_system_package).toHaveBeenCalledTimes(1);
  });

  it('displays unsupported repair path without a fake installation button',async()=>{
    const native={
      system_package_inventory:vi.fn(async()=>({
        ...snapshot,components:[{id:'video_tools',name:'FFmpeg and FFprobe',
          status:'missing',supplied_by:'not found',repair:null,
          required:true}],
      })),
      repair_system_package:vi.fn(),
    };
    render(<SystemReadinessPanel nativeBridge={native}/>);
    expect(await screen.findByText('FFmpeg and FFprobe')).toBeTruthy();
    expect(screen.getByText(/cannot be installed automatically/)).toBeTruthy();
    expect(screen.queryByText(/Ask to install FFmpeg/)).toBeNull();
    expect(native.repair_system_package).not.toHaveBeenCalled();
  });
});
