import React, { useState, useEffect, useRef } from 'react';
import config from './nvp_config.json';

const NvpDirectorDashboard = () => {
  const [projectId] = useState("PROJ_SCIFI_001");
  const [sceneId, setSceneId] = useState("SCENE_01");
  const [shotId, setShotId] = useState("SHOT_01A");
  const [scriptContext, setScriptContext] = useState("INT. SPACESHIP - DAY\n\nCommander Vance enters the airlock. He looks exhausted, scanning the blinking console.");
  const [cinematicStyle, setCinematicStyle] = useState("1970s Sci-Fi Anamorphic Noir");

  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Awaiting Director Execution");
  const [engineResults, setEngineResults] = useState(null);

  const [behavioralProgress, setBehavioralProgress] = useState(0);
  const [opticalProgress, setOpticalProgress] = useState(0);

  const abortControllerRef = useRef(null);

  useEffect(() => {
    let interval;
    if (isGenerating) {
      interval = setInterval(() => {
        setBehavioralProgress(prev => (prev < 90 ? prev + Math.random() * 15 : prev));
        setOpticalProgress(prev => (prev < 95 ? prev + Math.random() * 20 : prev));
      }, 300);
    } else {
      clearInterval(interval);
    }
    return () => clearInterval(interval);
  }, [isGenerating]);

  // Cleanup pending requests on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleGenerateScene = async () => {
    if (abortControllerRef.current) abortControllerRef.current.abort();
    abortControllerRef.current = new AbortController();

    setIsGenerating(true);
    setEngineResults(null);
    setBehavioralProgress(0);
    setOpticalProgress(0);
    setStatusMessage("Firing Parallel Inference Streams...");

    try {
      const url = `${config.api.baseUrl}${config.api.endpoints.engine.generateScene}`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          project_id: projectId,
          scene_id: sceneId,
          shot_id: shotId,
          script_context: scriptContext,
          cinematic_style: cinematicStyle
        })
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      
      const data = await response.json();
      
      setBehavioralProgress(100);
      setOpticalProgress(100);
      setEngineResults(data.data);
      setStatusMessage("Unreal Engine Nodes Synchronized.");
    } catch (error) {
      if (error.name === 'AbortError') {
        setStatusMessage("Execution Aborted.");
      } else {
        console.error("Pipeline failure:", error);
        setStatusMessage("Critical Error: Pipeline Execution Failed.");
      }
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-8 font-sans">
      <div className="max-w-6xl mx-auto space-y-6">
        
        <div className="bg-gray-800 border border-gray-700 p-6 rounded-xl shadow-lg flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white">Director's Execution Board</h1>
            <p className="text-sm text-gray-400 mt-1 font-mono">Workspace: {projectId} | Engine Status: <span className="text-green-400">ONLINE</span></p>
          </div>
          <div className="text-right">
            <div className={`text-sm font-mono px-3 py-1 rounded inline-block ${isGenerating ? 'bg-yellow-900 text-yellow-400 animate-pulse' : 'bg-gray-700 text-gray-300'}`}>
              {statusMessage}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1 space-y-6 bg-gray-800 border border-gray-700 p-6 rounded-xl shadow-lg">
            <h2 className="text-xl font-semibold border-b border-gray-700 pb-2">Scene Context</h2>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Scene ID</label>
                <input 
                  type="text" value={sceneId} onChange={e => setSceneId(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded p-2 text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Shot ID</label>
                <input 
                  type="text" value={shotId} onChange={e => setShotId(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded p-2 text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Enforced Style Matrix</label>
              <input 
                type="text" value={cinematicStyle} readOnly
                className="w-full bg-gray-900 border border-gray-700 rounded p-2 text-gray-400 cursor-not-allowed font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-blue-400 mb-1">Script Block (VLM Input)</label>
              <textarea 
                rows="5" value={scriptContext} onChange={e => setScriptContext(e.target.value)}
                className="w-full bg-gray-950 border border-gray-700 rounded p-2 text-white focus:outline-none focus:border-blue-500 font-mono text-sm resize-none"
              />
            </div>

            <button 
              onClick={handleGenerateScene}
              disabled={isGenerating}
              className={`w-full py-4 rounded font-bold tracking-wide transition-all ${isGenerating ? 'bg-gray-600 text-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_15px_rgba(37,99,235,0.4)]'}`}
            >
              {isGenerating ? "Processing Streams..." : "EXECUTE SCENE GENERATION"}
            </button>
          </div>

          <div className="lg:col-span-2 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-gray-800 border border-gray-700 p-6 rounded-xl shadow-lg">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-semibold text-purple-400">Node: Acting Coach</h3>
                  <span className="text-xs font-mono text-gray-500">VLM Engine</span>
                </div>
                <div className="w-full bg-gray-950 rounded-full h-2.5 mb-2 overflow-hidden">
                  <div className="bg-purple-500 h-2.5 rounded-full transition-all duration-300 ease-out" style={{ width: `${Math.min(behavioralProgress, 100)}%` }}></div>
                </div>
                <div className="text-right text-xs font-mono text-gray-400">{Math.floor(Math.min(behavioralProgress, 100))}%</div>
              </div>

              <div className="bg-gray-800 border border-gray-700 p-6 rounded-xl shadow-lg">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-semibold text-cyan-400">Node: DP Optics</h3>
                  <span className="text-xs font-mono text-gray-500">Physical Matrix</span>
                </div>
                <div className="w-full bg-gray-950 rounded-full h-2.5 mb-2 overflow-hidden">
                  <div className="bg-cyan-500 h-2.5 rounded-full transition-all duration-300 ease-out" style={{ width: `${Math.min(opticalProgress, 100)}%` }}></div>
                </div>
                <div className="text-right text-xs font-mono text-gray-400">{Math.floor(Math.min(opticalProgress, 100))}%</div>
              </div>
            </div>

            <div className="bg-gray-800 border border-gray-700 p-6 rounded-xl shadow-lg h-64 overflow-y-auto">
              <h3 className="text-sm font-semibold border-b border-gray-700 pb-2 mb-4 text-gray-400">Live Telemetry Output</h3>
              
              {!engineResults && !isGenerating && (
                <div className="text-gray-600 font-mono text-sm text-center py-8">
                  Awaiting execution. All systems idle.
                </div>
              )}

              {isGenerating && (
                <div className="space-y-2 font-mono text-xs text-gray-400">
                  <p className="text-purple-400">&gt; Allocating VLM tensors for behavioral analysis...</p>
                  <p className="text-cyan-400">&gt; Looking up optical matrix configurations for '{cinematicStyle}'...</p>
                </div>
              )}

              {engineResults && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-gray-950 p-4 rounded border border-gray-700">
                    <h4 className="text-xs font-bold text-purple-400 mb-2">Behavioral Vectors Received</h4>
                    <pre className="text-xs font-mono text-gray-300 overflow-x-auto">
                      {JSON.stringify(engineResults.acting_parameters, null, 2)}
                    </pre>
                  </div>
                  <div className="bg-gray-950 p-4 rounded border border-gray-700">
                    <h4 className="text-xs font-bold text-cyan-400 mb-2">Optical Config Received</h4>
                    <pre className="text-xs font-mono text-gray-300 overflow-x-auto">
                      {JSON.stringify(engineResults.dp_configuration, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NvpDirectorDashboard;