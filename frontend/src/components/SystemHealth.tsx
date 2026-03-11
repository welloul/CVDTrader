import React from 'react';
import { useStore } from '../store/useStore';
import { Activity, Server, Clock } from 'lucide-react';

interface Props {
    wsConnected: boolean;
}

const SystemHealth: React.FC<Props> = ({ wsConnected }) => {
    const isRunning = useStore(state => state.isRunning);
    // Using an arbitrary latency placeholder. Real app would read from WS stream.
    const latencyMs = useStore(() => 42.5); // Example
    const positions = useStore(state => state.positions) || {};
    const positionCount = Object.keys(positions).length;

    return (
        <div className="bg-panel rounded-xl border border-gray-800 p-4">
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
                <Activity className="w-5 h-5 text-blue-400" /> System Health
            </h3>

            <div className="space-y-4">
                <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-400 flex items-center gap-2">
                        <Server className="w-4 h-4" /> API Link
                    </span>
                    <span className={`text-sm font-medium px-2 py-0.5 rounded ${wsConnected ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                        {wsConnected ? 'Connected' : 'Disconnected'}
                    </span>
                </div>

                <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-400 flex items-center gap-2">
                        <Clock className="w-4 h-4" /> Latency
                    </span>
                    <span className="text-sm font-medium font-mono text-gray-200">
                        {latencyMs} ms
                    </span>
                </div>

                <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-400 flex items-center gap-2">
                        <Activity className="w-4 h-4" /> Strategy Status
                    </span>
                    <span className={`text-sm font-medium ${isRunning ? 'text-accent' : 'text-gray-500'}`}>
                        {isRunning ? 'Running' : 'Halted'}
                    </span>
                </div>

                <div className="pt-3 border-t border-gray-800">
                    <div className="flex justify-between items-center mb-2">
                        <span className="text-sm text-gray-400">Open Positions</span>
                        <span className="text-md font-bold text-gray-200">{positionCount}</span>
                    </div>
                    {Object.values(positions).map((pos: any) => (
                        <div key={pos.coin} className="flex justify-between items-center text-xs font-mono py-1 border-t border-gray-800/50">
                            <span className="text-gray-300">
                                {pos.coin} <span className={pos.size > 0 ? 'text-accent' : 'text-danger'}>{pos.size > 0 ? 'LONG' : 'SHORT'}</span>
                            </span>
                            <span className="text-gray-500">${pos.entry_price?.toLocaleString()}</span>
                            <span className={`font-bold ${(pos.unrealized_pnl || 0) >= 0 ? 'text-accent' : 'text-danger'}`}>
                                {(pos.unrealized_pnl || 0) >= 0 ? '+' : ''}{(pos.unrealized_pnl || 0).toFixed(2)}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default SystemHealth;
