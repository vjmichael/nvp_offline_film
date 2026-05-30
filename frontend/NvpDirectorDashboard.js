JavaScript
import React, { useState } from 'react';

const NvpDirectorDashboard = () => {
    const [diagStatus, setDiagStatus] = useState(null);
    const [isChecking, setIsChecking] = useState(false);

    const runSystemDiagnostics = async () => {
        setIsChecking(true);
        try {
            const response = await fetch('http://localhost:8000/api/verify_system');
            const data = await response.json();
            setDiagStatus(data);
        } catch (error) {
            setDiagStatus({
                status: "critical",
                details: { main_api: "Offline (Backend Unreachable)" }
            });
        }
        setIsChecking(false);
    };

    return (
        <div style={{ backgroundColor: '#0a0a0a', color: '#fff', minHeight: '100vh', padding: '20px', fontFamily: 'sans-serif' }}>
            <header style={{ borderBottom: '1px solid #333', paddingBottom: '20px' }}>
                <h1 style={{ color: '#00ffcc' }}>NVP DIRECTOR DASHBOARD v2</h1>
            </header>

            <div style={{ marginTop: '20px', width: '300px', background: '#111', padding: '15px', borderRadius: '8px' }}>
                <h3 style={{ fontSize: '14px', color: '#888' }}>SYSTEM MAINTENANCE</h3>
                <button 
                    onClick={runSystemDiagnostics}
                    disabled={isChecking}
                    style={{
                        width: '100%',
                        padding: '12px',
                        backgroundColor: '#1a1a1a',
                        color: '#00ffcc',
                        border: '1px solid #00ffcc',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontWeight: 'bold',
                        marginTop: '10px'
                    }}
                >
                    {isChecking ? "EXECUTING SCAN..." : "RUN SYSTEM DIAGNOSTICS"}
                </button>

                {diagStatus && (
                    <div style={{ 
                        marginTop: '15px', 
                        padding: '10px', 
                        backgroundColor: '#000', 
                        border: `1px solid ${diagStatus.status === 'optimal' ? '#00ff00' : '#ff0055'}`,
                        borderRadius: '4px',
                        fontSize: '12px'
                    }}>
                        <div style={{ color: diagStatus.status === 'optimal' ? '#00ff00' : '#ff0055', fontWeight: 'bold' }}>
                            STATUS: {diagStatus.status.toUpperCase()}
                        </div>
                        <ul style={{ listStyle: 'none', padding: 0, marginTop: '8px' }}>
                            {Object.entries(diagStatus.details).map(([key, val]) => (
                                <li key={key} style={{ color: '#ccc', marginBottom: '4px' }}>
                                    <span style={{ color: '#fff' }}>{key.replace('_', ' ')}:</span> {val}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        </div>
    );
};

export default NvpDirectorDashboard;
