import React, { useEffect, useState } from 'react';
import { useStore } from '../store/useStore';
import ChartWidget from './ChartWidget';
import SystemHealth from './SystemHealth';
import LiveLogs from './LiveLogs';
import ControlPanel from './ControlPanel';
import CandleHistory from './CandleHistory';
import TradeHistory from './TradeHistory';

const Dashboard: React.FC = () => {
    const updateState = useStore((state) => state.updateState);
    const executionMode = useStore((s) => s.config?.execution_mode);
    const activeStrategy = useStore((s) => s.config?.active_strategy);
    const walletBalance = useStore((s) => s.walletBalance);

    const [wsConnected, setWsConnected] = useState(false);

    useEffect(() => {
        let ws: WebSocket | null = null;
        let retryDelay = 1000;
        let retryTimer: ReturnType<typeof setTimeout> | null = null;
        let destroyed = false;

        const connect = () => {
            if (destroyed) return;
            ws = new WebSocket('ws://localhost:8000/ws');

            ws.onopen = () => {
                setWsConnected(true);
                retryDelay = 1000; // reset backoff on success
            };

            ws.onclose = () => {
                setWsConnected(false);
                if (!destroyed) {
                    retryTimer = setTimeout(() => {
                        retryDelay = Math.min(retryDelay * 2, 10000);
                        connect();
                    }, retryDelay);
                }
            };

            ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    if (message.type === 'state_update') {
                        updateState({
                            isRunning: message.data.is_running,
                            walletBalance: message.data.wallet_balance ?? 0,
                            positions: message.data.positions ?? {},
                            activeOrders: message.data.active_orders ?? {},
                            config: message.data.config ?? {},
                            market_data: message.data.market_data ?? {},
                            logs: message.data.logs ?? [],
                            closedTrades: message.data.closed_trades ?? [],
                            totalPnl: message.data.total_pnl ?? 0
                        });
                    }
                } catch (err) {
                    console.error('Error parsing WS message', err);
                }
            };
        };

        connect();

        return () => {
            destroyed = true;
            if (retryTimer) clearTimeout(retryTimer);
            ws?.close();
        };
    }, [updateState]);

    return (
        <div className="p-4 grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 h-screen max-w-7xl mx-auto">
            {/* Header spanning full width */}
            <div className="col-span-full flex items-center justify-between p-4 bg-panel rounded-xl border border-gray-800">
                <h1 className="text-2xl font-bold text-gray-100 flex items-center gap-3">
                    CVDTrader Pro <span className="text-[10px] text-gray-600">v1.1-fix</span>
                    <span className={`h-3 w-3 rounded-full ${wsConnected ? 'bg-accent shadow-[0_0_8px_#2ebd85]' : 'bg-danger shadow-[0_0_8px_#e0294a]'}`} />

                    {executionMode && (
                        <span className={`text-xs px-2 py-0.5 rounded uppercase font-bold ${executionMode === 'live' ? 'bg-red-900/40 text-red-100 border border-red-800' :
                            executionMode === 'testnet' ? 'bg-blue-900/40 text-blue-100 border border-blue-800' :
                                'bg-gray-800 text-gray-300 border border-gray-700'
                            }`}>
                            {executionMode}
                        </span>
                    )}

                    {activeStrategy && (
                        <span className="text-xs px-2 py-0.5 rounded uppercase font-bold bg-purple-900/40 text-purple-100 border border-purple-800">
                            Strategy: {activeStrategy.replace('_', ' ')}
                        </span>
                    )}
                </h1>
                <div className="flex items-center gap-6">
                    <div className="flex bg-gray-900/50 p-1 rounded-lg border border-gray-800">
                        {['BTC', 'ETH', 'SOL', 'BNB', 'BCH', 'ZEC', 'XMR', 'LTC'].map(coin => (
                            <button
                                key={coin}
                                onClick={() => useStore.getState().setSelectedCoin(coin)}
                                className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${useStore.getState().selectedCoin === coin
                                    ? 'bg-accent text-[#0b0e14]'
                                    : 'text-gray-400 hover:text-gray-200'
                                    }`}
                            >
                                {coin}
                            </button>
                        ))}
                    </div>
                    <div className="text-sm text-gray-400">
                        Balance: <span className="text-accent font-mono font-bold">${(walletBalance ?? 0).toFixed(2)}</span>
                    </div>
                </div>
            </div>

            {/* Main Chart Widget taking most space */}
            <div className="col-span-1 md:col-span-2 lg:col-span-3 row-span-2 bg-panel rounded-xl border border-gray-800 overflow-hidden flex flex-col">
                <ChartWidget />
            </div>

            {/* Side panel constraints & controls */}
            <div className="col-span-1 flex flex-col gap-4">
                <SystemHealth wsConnected={wsConnected} />
                <ControlPanel />
            </div>

            {/* Bottom Row: Logs, Candle Data, Trade History */}
            <div className="col-span-full lg:col-span-1 h-64 bg-panel rounded-xl border border-gray-800 p-4 font-mono text-sm overflow-hidden">
                <LiveLogs />
            </div>
            <div className="col-span-full lg:col-span-1 h-64 bg-panel rounded-xl border border-gray-800 p-4 font-mono text-sm overflow-hidden">
                <CandleHistory />
            </div>
            <div className="col-span-full lg:col-span-2 h-64 bg-panel rounded-xl border border-gray-800 p-4 overflow-hidden">
                <TradeHistory />
            </div>
        </div>
    );
};

export default Dashboard;
