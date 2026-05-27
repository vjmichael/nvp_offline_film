import React, { useState } from 'react';
import NvpProjectWizard from './NvpProjectWizard';
import NvpDirectorDashboard from './NvpDirectorDashboard';
import NvpVersionControlPanel from './NvpVersionControlPanel';
import NvpReconstructedPanel from './NvpReconstructedPanel'; // Your existing component

const App = () => {
  const [activeModule, setActiveModule] = useState('wizard');
  const [globalProjectId, setGlobalProjectId] = useState(null);

  const handleProjectInitialization = (projectId) => {
    setGlobalProjectId(projectId);
    setActiveModule('dashboard');
  };

  return (
    <div className="flex h-screen bg-black text-gray-100 font-sans overflow-hidden">
      
      {/* Global OS Sidebar */}
      <div className="w-64 bg-gray-950 border-r border-gray-800 flex flex-col justify-between z-10 shadow-2xl">
        <div>
          <div className="p-6 border-b border-gray-800">
            <h1 className="text-xl font-bold tracking-widest text-white">NVP OS</h1>
            <p className="text-xs text-gray-500 font-mono mt-1">v0.1.0-alpha</p>
          </div>

          <nav className="p-4 space-y-2">
            <button 
              onClick={() => setActiveModule('wizard')}
              className={`w-full text-left px-4 py-3 rounded-lg text-sm font-semibold transition-all ${activeModule === 'wizard' ? 'bg-blue-900/50 text-blue-400 border border-blue-800/50' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200 border border-transparent'}`}
            >
              ⬡ Project Architect
            </button>

            <button 
              onClick={() => setActiveModule('dashboard')}
              disabled={!globalProjectId}
              className={`w-full text-left px-4 py-3 rounded-lg text-sm font-semibold transition-all ${!globalProjectId ? 'opacity-50 cursor-not-allowed text-gray-600' : activeModule === 'dashboard' ? 'bg-purple-900/50 text-purple-400 border border-purple-800/50' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200 border border-transparent'}`}
            >
              ⊞ Execution Dashboard
            </button>

            <button 
              onClick={() => setActiveModule('reconstruction')}
              disabled={!globalProjectId}
              className={`w-full text-left px-4 py-3 rounded-lg text-sm font-semibold transition-all ${!globalProjectId ? 'opacity-50 cursor-not-allowed text-gray-600' : activeModule === 'reconstruction' ? 'bg-cyan-900/50 text-cyan-400 border border-cyan-800/50' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200 border border-transparent'}`}
            >
              ◮ 3D Reconstruction
            </button>

            <button 
              onClick={() => setActiveModule('versionControl')}
              disabled={!globalProjectId}
              className={`w-full text-left px-4 py-3 rounded-lg text-sm font-semibold transition-all ${!globalProjectId ? 'opacity-50 cursor-not-allowed text-gray-600' : activeModule === 'versionControl' ? 'bg-green-900/50 text-green-400 border border-green-800/50' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200 border border-transparent'}`}
            >
              ◫ Production Ledger
            </button>
          </nav>
        </div>

        <div className="p-6 border-t border-gray-800 bg-gray-900/50">
          <p className="text-xs text-gray-500 font-mono mb-1">ACTIVE WORKSPACE</p>
          {globalProjectId ? (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <p className="text-sm font-bold text-green-400 truncate">{globalProjectId}</p>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-red-500 rounded-full"></div>
              <p className="text-sm font-bold text-red-500">NO PROJECT LOCKED</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-gray-900 relative">
        {activeModule === 'wizard' && (
          <NvpProjectWizard onProjectLocked={handleProjectInitialization} />
        )}
        
        {activeModule === 'dashboard' && globalProjectId && (
          <NvpDirectorDashboard projectId={globalProjectId} />
        )}

        {activeModule === 'reconstruction' && globalProjectId && (
          <div className="p-8 h-full">
            <NvpReconstructedPanel projectId={globalProjectId} />
          </div>
        )}

        {activeModule === 'versionControl' && globalProjectId && (
          <div className="p-8 h-full">
            <NvpVersionControlPanel projectId={globalProjectId} />
          </div>
        )}
      </div>
    </div>
  );
};

export default App;