import React, { useState } from 'react';

const NvpReconstructionPanel = ({ projectId, availablePlates }) => {
    const [selectedPlate, setSelectedPlate] = useState('');
    const [sceneName, setSceneName] = useState('');
    const [showWarning, setShowWarning] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);

    const handleAcknowledgeAndExecute = async () => {
        setShowWarning(false);
        setIsProcessing(true);

        const payload = {
            project_id: projectId,
            reference_plate_id: selectedPlate,
            target_scene_id: sceneName || "Converted_Scene_01"
        };

        try {
            const response = await fetch("http://localhost:8000/api/engine/reconstruct_spatial", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            console.log("Reconstruction Complete:", data);
        } catch (error) {
            console.error("VRAM Overflow or Pipeline Failure:", error);
        } finally {
            setIsProcessing(false);
        }
    };

    return (
        <div className="border border-zinc-800 p-6 rounded bg-black text-zinc-200">
            <h2 className="text-xl font-bold mb-4">Zero-Shot 2D-to-3D Reconstruction</h2>
            
            <div className="flex flex-col gap-4 mb-6">
                <select 
                    className="bg-zinc-900 border border-zinc-700 p-2 rounded"
                    value={selectedPlate} 
                    onChange={(e) => setSelectedPlate(e.target.value)}
                >
                    <option value="">Select 2D Legacy Plate...</option>
                    {availablePlates.map(plate => (
                        <option key={plate.id} value={plate.id}>{plate.id} - {plate.description}</option>
                    ))}
                </select>

                <input 
                    type="text" 
                    placeholder="Target 3D Scene ID (e.g., SC_01_Spatial)"
                    className="bg-zinc-900 border border-zinc-700 p-2 rounded"
                    value={sceneName}
                    onChange={(e) => setSceneName(e.target.value)}
                />
            </div>

            <button 
                className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 px-4 rounded w-full disabled:opacity-50"
                disabled={!selectedPlate || isProcessing}
                onClick={() => setShowWarning(true)}
            >
                {isProcessing ? "Synthesizing Spatial Volume (VRAM High)..." : "Compile Spatial Volume"}
            </button>

            {/* The Gatekeeper Modal */}
            {showWarning && (
                <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
                    <div className="bg-zinc-900 border border-red-900 p-6 rounded max-w-md">
                        <h3 className="text-red-500 font-bold text-lg mb-2">Hardware Demand Warning</h3>
                        <p className="text-sm text-zinc-400 mb-4">
                            You are about to initiate a multi-model transformer pipeline (Depth + SAM + SV3D). 
                            This will bypass standard 2D rendering and immediately push GPU utilization to 100%. 
                        </p>
                        <p className="text-sm text-zinc-400 mb-6">
                            Ensure no other heavy Unreal Engine instances are compiling, or your system may encounter a hard VRAM stall.
                        </p>
                        <div className="flex gap-4">
                            <button 
                                className="bg-zinc-700 hover:bg-zinc-600 px-4 py-2 rounded text-sm w-full"
                                onClick={() => setShowWarning(false)}
                            >
                                Cancel
                            </button>
                            <button 
                                className="bg-red-700 hover:bg-red-600 font-bold px-4 py-2 rounded text-sm w-full"
                                onClick={handleAcknowledgeAndExecute}
                            >
                                I Understand the Risks
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default NvpReconstructionPanel;