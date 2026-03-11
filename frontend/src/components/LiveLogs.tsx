import React, { useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';

const LiveLogs: React.FC = () => {
    const logs = useStore(state => state.logs);
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);

    const getLevelColor = (level: string) => {
        switch (level) {
            case 'INFO': return 'text-blue-400';
            case 'WARN': return 'text-yellow-400';
            case 'ERROR': return 'text-red-400';
            default: return 'text-gray-400';
        }
    };

    return (
        <div className="h-full flex flex-col">
            <div className="flex justify-between items-center mb-2 pb-2 border-b border-gray-800">
                <h3 className="font-semibold text-gray-300">Live Execution Logs</h3>
                <span className="text-xs text-gray-500 font-mono">Tail: 50 lines</span>
            </div>
            <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-1 pr-2 custom-scrollbar">
                {logs.map((log, i) => (
                    <div key={i} className="flex gap-3 font-mono text-xs hover:bg-white/5 p-0.5 rounded">
                        <span className="text-gray-500 w-24 shrink-0">{log.timestamp}</span>
                        <span className={`w-10 shrink-0 font-bold ${getLevelColor(log.level)}`}>{log.level}</span>
                        <span className="text-gray-300 flex-1">{log.message}</span>
                        <span className="text-gray-500 shrink-0">{log.latency ? `latency=${log.latency}` : ''}</span>
                    </div>
                ))}
                {logs.length === 0 && (
                    <div className="text-gray-600 text-sm italic">Waiting for log stream...</div>
                )}
            </div>
        </div>
    );
};

export default LiveLogs;
