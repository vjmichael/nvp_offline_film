import React from 'react';
import NvpTouchlessAudio from './NvpTouchlessAudio';
import NvpReconstructedPanel from './NvpReconstructedPanel';

export default function NvpDirectorDashboard() {
  return (
    <div className="min-h-screen bg-black p-8 flex flex-col gap-6 font-mono">
      <header className="border-b border-zinc-800 pb-4">
        <h1 className="text-2xl font-bold text-white tracking-tight">NVP Director Dashboard</h1>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {/* Main viewport streaming UE5 telemetry via NDI/Pixel Streaming */}
          <div className="aspect-video bg-zinc-900 rounded-lg flex items-center justify-center border border-zinc-800">
            <span className="text-zinc-600 font-bold uppercase tracking-widest">Live UE5 Viewport Active</span>
          </div>
          
          <NvpTouchlessAudio />
        </div>

        <div className="space-y-6">
          <NvpReconstructedPanel />
          {/* Future Version Control & Daily ledgers go here */}
        </div>
      </div>
    </div>
  );
}