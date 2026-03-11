import React, { useState } from 'react';
import { useStore } from '../store/useStore';
import { Play, Square, Settings, ShieldAlert } from 'lucide-react';

const ControlPanel: React.FC = () => {
    const isRunning = useStore(state => state.isRunning);
    const config = useStore(state => state.config);

    // Local state for forms
    const [leverage, setLeverage] = useState(config?.max_leverage || 5);
    const [maxSize, setMaxSize] = useState(config?.max_position_size_usd || 1000);

    const toggleBot = async () => {
        const endpoint = isRunning ? '/api/stop' : '/api/start';
        try {
            await fetch(`http://localhost:8000${endpoint}`, { method: 'POST' });
        } catch (err) {
            console.error('Failed to toggle bot', err);
        }
    };

    const saveConfig = async () => {
        try {
            await fetch('http://localhost:8000/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    max_leverage: leverage,
                    max_position_size_usd: maxSize
                }),
            });
        } catch (err) {
            console.error('Config save failed', err);
        }
    };

    return (
        <div className="bg-panel rounded-xl border border-gray-800 p-4 flex flex-col gap-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
                <Settings className="w-5 h-5 text-accent" /> Control Panel
            </h3>

            <div className="flex gap-2">
                <button
                    onClick={toggleBot}
                    className={`flex-1 py-2 rounded-lg font-bold flex justify-center items-center gap-2 transition-colors ${isRunning
                        ? 'bg-danger/20 text-danger hover:bg-danger/30 border border-danger/50'
                        : 'bg-accent/20 text-accent hover:bg-accent/30 border border-accent/50'
                        }`}
                >
                    {isRunning ? <><Square className="w-4 h-4 fill-current" /> STOP</> : <><Play className="w-4 h-4 fill-current" /> START</>}
                </button>
            </div>

            <div className="space-y-3 mt-2">
                <div>
                    <label className="text-xs text-gray-500 mb-1 block">Max Leverage (x)</label>
                    <input
                        type="number"
                        value={leverage}
                        onChange={(e) => setLeverage(Number(e.target.value))}
                        className="w-full bg-[#0b0e14] border border-gray-700 rounded-md py-1 px-3 text-sm focus:outline-none focus:border-accent"
                    />
                </div>
                <div>
                    <label className="text-xs text-gray-500 mb-1 block">Max Pos Size (USD)</label>
                    <input
                        type="number"
                        value={maxSize}
                        onChange={(e) => setMaxSize(Number(e.target.value))}
                        className="w-full bg-[#0b0e14] border border-gray-700 rounded-md py-1 px-3 text-sm focus:outline-none focus:border-accent"
                    />
                </div>
                <button
                    onClick={saveConfig}
                    className="w-full bg-gray-800 hover:bg-gray-700 text-sm py-1.5 rounded-md transition-colors border border-gray-700"
                >
                    Update Risk Params
                </button>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-800">
                <button className="w-full bg-red-900/40 hover:bg-red-900/60 text-red-400 text-sm py-2 rounded-md font-semibold border border-red-800/50 flex items-center justify-center gap-2">
                    <ShieldAlert className="w-4 h-4" /> EMERGENCY KILL
                </button>
            </div>
        </div>
    );
};

export default ControlPanel;
