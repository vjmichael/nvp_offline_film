import React, { useState } from 'react';
import config from './nvp_config.json';

const NvpProjectWizard = ({ onProjectLocked }) => {
  const [projectId, setProjectId] = useState('PROJ_SCIFI_001');
  const [customPath, setCustomPath] = useState('');
  const [showManualPath, setShowManualPath] = useState(false);
  
  const [checkStatus, setCheckStatus] = useState('idle'); // idle, checking, success, failed
  const [logs, setLogs] = useState([]);
  const [errors, setErrors] = useState([]);

  const runIntegrityCheck = async () => {
    setCheckStatus('checking');
    setLogs(["Initiating System Pre-Flight Check..."]);
    setErrors([]);

    try {
      // In production, this hits the FastAPI endpoint we just defined
      // const response = await fetch(`${config.api.baseUrl}/project/verify_integrity`, { ... });
      
      // -- MOCKING BACKEND RESPONSE FOR UI DEMONSTRATION --
      await new Promise(r => setTimeout(r, 1200)); 
      
      // Simulate backend auto-guessing the path
      const activePath = customPath || `C:/NVP_Projects/${projectId}`;
      
      // Simulate a failure if the path isn't specifically our demo path
      if (!customPath && projectId !== 'PROJ_SCIFI_001') {
         setErrors([
           `Project directory not found at ${activePath}`,
           "No .uproject file detected."
         ]);
         setLogs([
           `Targeting UE5 Path: ${activePath}`,
           "Critical failure attempting to locate root directory."
         ]);
         setCheckStatus('failed');
         setShowManualPath(true); // Pop open the manual override
         return;
      }

      // Simulate Success Flow
      setLogs([
        `Targeting UE5 Path: ${activePath}`,
        "Project directory located.",
        "Validated .uproject file.",
        "NVP UE5 Python Bridge missing. Attempting auto-injection...",
        "Auto-injection successful. Bridge connected.",
        "Local JSON payload directory is ready and writable."
      ]);
      setCheckStatus('success');

    } catch (err) {
      setErrors(["Network error contacting NVP Backend."]);
      setCheckStatus('failed');
    }
  };

  const handleLockProject = () => {
    if (checkStatus === 'success') {
      onProjectLocked(projectId);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-900 p-8">
      <div className="w-full max-w-2xl bg-gray-800 border border-gray-700 rounded-xl shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="bg-gray-950 p-6 border-b border-gray-700">
          <h2 className="text-2xl font-bold text-white tracking-wide">Workspace Initialization</h2>
          <p className="text-sm text-gray-400 mt-1">Configure and verify the Unreal Engine 5 integration.</p>
        </div>

        <div className="p-8 space-y-8">
          
          {/* Project ID Input */}
          <div>
            <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Project ID (Nomenclature)</label>
            <input 
              type="text" 
              value={projectId} 
              onChange={e => {
                setProjectId(e.target.value);
                setCheckStatus('idle'); // Reset check if ID changes
              }}
              className="w-full bg-gray-950 border border-gray-700 rounded p-3 text-white focus:outline-none focus:border-blue-500 font-mono"
            />
            <p className="text-xs text-gray-500 mt-2">The system will attempt to mathematically guess the directory path based on this ID.</p>
          </div>

          {/* Manual Path Fallback (Conditionally Rendered) */}
          {showManualPath && (
            <div className="bg-red-900/20 border border-red-800/50 p-4 rounded animate-fade-in">
              <label className="block text-xs font-bold text-red-400 uppercase mb-2">Manual Directory Override</label>
              <input 
                type="text" 
                value={customPath} 
                onChange={e => setCustomPath(e.target.value)}
                placeholder="e.g., D:/MyCustomProjects/SciFi_Movie"
                className="w-full bg-gray-950 border border-red-800/50 rounded p-3 text-white focus:outline-none focus:border-red-500 font-mono text-sm"
              />
              <p className="text-[10px] text-red-400 mt-1">Auto-detect failed. Please provide the exact path to the folder containing the .uproject file.</p>
            </div>
          )}

          {/* Pre-Flight Terminal */}
          <div className="bg-black border border-gray-700 rounded p-4 font-mono text-xs h-48 overflow-y-auto shadow-inner">
            <h3 className="text-gray-500 mb-3 border-b border-gray-800 pb-1">-- NVP Integrity Logs --</h3>
            
            {logs.length === 0 && <p className="text-gray-700 italic">Awaiting pre-flight execution...</p>}
            
            {logs.map((log, i) => (
              <p key={i} className="text-gray-300 mb-1"><span className="text-blue-500">&gt;</span> {log}</p>
            ))}

            {errors.map((err, i) => (
              <p key={i} className="text-red-500 mb-1 font-bold"><span className="text-red-700">[ERROR]</span> {err}</p>
            ))}

            {checkStatus === 'checking' && (
              <p className="text-yellow-500 animate-pulse mt-2">Running diagnostics...</p>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex gap-4 pt-4 border-t border-gray-700">
            <button 
              onClick={runIntegrityCheck}
              disabled={checkStatus === 'checking'}
              className="flex-1 bg-gray-700 hover:bg-gray-600 text-white py-3 rounded font-bold tracking-wide transition-colors disabled:opacity-50"
            >
              Run Integrity Check
            </button>

            <button 
              onClick={handleLockProject}
              disabled={checkStatus !== 'success'}
              className={`flex-1 py-3 rounded font-bold tracking-wide transition-all ${checkStatus === 'success' ? 'bg-green-600 hover:bg-green-500 text-white shadow-[0_0_15px_rgba(22,163,74,0.4)]' : 'bg-gray-800 text-gray-500 cursor-not-allowed'}`}
            >
              Lock & Initialize OS
            </button>
          </div>

        </div>
      </div>
    </div>
  );
};

export default NvpProjectWizard;