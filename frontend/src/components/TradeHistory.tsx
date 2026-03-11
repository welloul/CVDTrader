import React from 'react';
import { useStore } from '../store/useStore';
import type { ClosedTrade } from '../store/useStore';

const TradeHistory: React.FC = () => {
    const closedTrades = useStore((s) => s.closedTrades);
    const totalPnl = useStore((s) => s.totalPnl);

    const wins = closedTrades.filter((t) => t.pnl > 0).length;
    const losses = closedTrades.filter((t) => t.pnl <= 0).length;
    const winRate = closedTrades.length > 0 ? ((wins / closedTrades.length) * 100).toFixed(1) : '—';

    const formatTime = (iso: string) => {
        try {
            return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch {
            return iso;
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header row */}
            <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-bold text-gray-300 uppercase tracking-wider">Trade History</h2>
                <div className="flex gap-4 text-xs font-mono">
                    <span className="text-gray-500">
                        W/L: <span className="text-green-400">{wins}</span>/<span className="text-red-400">{losses}</span>
                        {closedTrades.length > 0 && <span className="text-gray-400"> ({winRate}%)</span>}
                    </span>
                    <span className={`font-bold ${totalPnl >= 0 ? 'text-accent' : 'text-danger'}`}>
                        Total PnL: {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(4)} USD
                    </span>
                </div>
            </div>

            {/* Table */}
            {closedTrades.length === 0 ? (
                <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">
                    No closed trades yet
                </div>
            ) : (
                <div className="flex-1 overflow-y-auto">
                    <table className="w-full text-xs font-mono border-collapse">
                        <thead>
                            <tr className="text-gray-500 border-b border-gray-800">
                                <th className="text-left py-1 pr-2">Time</th>
                                <th className="text-left py-1 pr-2">Coin</th>
                                <th className="text-left py-1 pr-2">Side</th>
                                <th className="text-right py-1 pr-2">Entry</th>
                                <th className="text-right py-1 pr-2">Exit</th>
                                <th className="text-right py-1 pr-2">Size</th>
                                <th className="text-right py-1 pr-2">PnL</th>
                                <th className="text-left py-1">Reason</th>
                            </tr>
                        </thead>
                        <tbody>
                            {[...closedTrades].reverse().map((trade: ClosedTrade) => (
                                <tr key={trade.id} className="border-b border-gray-900 hover:bg-gray-900/40">
                                    <td className="py-1 pr-2 text-gray-500">{formatTime(trade.closed_at)}</td>
                                    <td className="py-1 pr-2 text-gray-200 font-bold">{trade.coin}</td>
                                    <td className={`py-1 pr-2 font-bold ${trade.side === 'LONG' ? 'text-accent' : 'text-red-400'}`}>
                                        {trade.side}
                                    </td>
                                    <td className="py-1 pr-2 text-right text-gray-300">${trade.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                                    <td className="py-1 pr-2 text-right text-gray-300">${trade.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                                    <td className="py-1 pr-2 text-right text-gray-400">{trade.size.toFixed(5)}</td>
                                    <td className={`py-1 pr-2 text-right font-bold ${trade.pnl >= 0 ? 'text-accent' : 'text-red-400'}`}>
                                        {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(4)}
                                    </td>
                                    <td className="py-1 text-gray-500 truncate max-w-[120px]" title={trade.reason}>{trade.reason}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

export default TradeHistory;
