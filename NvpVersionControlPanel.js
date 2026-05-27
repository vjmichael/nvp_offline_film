import React, { useState, useEffect, useCallback } from 'react';
import config from './nvp_config.json';

const NvpVersionControlPanel = ({ projectId }) => {
  const [dailies, setDailies] = useState({ floating_takes: [], hourly_snapshots: [] });
  const [isLoading, setIsLoading] = useState(false);

  const fetchLedger = useCallback(async () => {
    setIsLoading(true);
    try {
      const url = `${config.api.baseUrl}${config.api.endpoints.versioning.getLedger}?project_id=${projectId}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch ledger");
      const data = await response.json();
      setDailies(data);
    } catch (err) {
      console.error("Ledger sync failed:", err);
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  const triggerSnapshot = async () => {
    try {
      const url = `${config.api.baseUrl}${config.api.endpoints.versioning.snapshot}`;
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId })
      });
      fetchLedger();
    } catch (err) {
      console.error("Snapshot commit failed:", err);
    }
  };

  useEffect(() => { 
    fetchLedger(); 
  }, [fetchLedger]);

  return (
    <div className="bg-gray-900 text-gray-100 p-6 rounded-xl border border-gray-700 h-full flex flex-col">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold text-white tracking-wide">Production Ledger</h2>
        <button 
          onClick={triggerSnapshot}
          disabled={isLoading}
          className={`px-4 py-2 rounded text-sm font-semibold transition-colors ${isLoading ? 'bg-gray-600 cursor-not-allowed' : 'bg-purple-700 hover:bg-purple-600'}`}
        >
          {isLoading ? 'Syncing...' : 'Commit Hourly Snapshot'}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-6 flex-grow">
        <div className="bg-gray-950 p-4 rounded border border-gray-700 overflow-y-auto">
          <h3 className="text-xs font-bold text-gray-400 uppercase mb-4">Live Floating Takes</h3>
          {dailies.floating_takes.length === 0 && (
            <p className="text-xs text-gray-600 italic">No floating takes currently active.</p>
          )}
          {dailies.floating_takes.map((take) => (
            <div key={take.take_uid} className="bg-gray-800 p-3 mb-2 rounded border border-gray-700 hover:border-blue-500 transition-colors">
              <div className="flex justify-between text-xs">
                <span className="font-mono text-blue-400">{take.take_uid}</span>
                <span className="text-gray-500">{take.camera_id}</span>
              </div>
              <p className="text-[10px] text-gray-400 mt-1">{take.timestamp}</p>
            </div>
          ))}
        </div>

        <div className="bg-gray-950 p-4 rounded border border-gray-700 overflow-y-auto">
          <h3 className="text-xs font-bold text-gray-400 uppercase mb-4">Immutable Snapshots</h3>
          {dailies.hourly_snapshots.length === 0 && (
            <p className="text-xs text-gray-600 italic">No snapshots committed yet.</p>
          )}
          {dailies.hourly_snapshots.map((snap) => (
            <div key={snap.snapshot_id} className="bg-gray-800 p-3 mb-2 rounded border border-gray-700 cursor-pointer hover:bg-gray-700">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-green-400">{snap.snapshot_id}</span>
                <span className="text-[10px] text-gray-500">{snap.takes.length} takes</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default NvpVersionControlPanel;