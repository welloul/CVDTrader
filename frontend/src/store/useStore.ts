import { create } from 'zustand';

interface Position {
    coin: string;
    size: number;
    entry_price: number;
    leverage: number;
    unrealized_pnl: number;
}

interface ActiveOrder {
    oid: number;
    coin: string;
    is_buy: boolean;
    sz: number;
    limit_px: number;
    order_type: string;
}

interface BotConfig {
    max_leverage: number;
    max_position_size_usd: number;
    max_drawdown_pct: number;
    execution_mode?: string;
    active_strategy?: string;
}

interface LogEntry {
    timestamp: string;
    level: string;
    message: string;
    [key: string]: any;
}

export interface ClosedTrade {
    id: string;
    coin: string;
    side: string;
    size: number;
    entry_price: number;
    exit_price: number;
    pnl: number;
    reason: string;
    opened_at: string;
    closed_at: string;
}

interface AppState {
    isRunning: boolean;
    walletBalance: number;
    positions: Record<string, Position>;
    activeOrders: Record<string, ActiveOrder>;
    config: BotConfig;
    market_data: Record<string, any>;
    selectedCoin: string;
    logs: LogEntry[];
    closedTrades: ClosedTrade[];
    totalPnl: number;
    setRunning: (status: boolean) => void;
    setSelectedCoin: (coin: string) => void;
    updateState: (data: Partial<AppState>) => void;
}

export const useStore = create<AppState>((set) => ({
    isRunning: false,
    walletBalance: 0,
    positions: {},
    activeOrders: {},
    config: {
        max_leverage: 5,
        max_position_size_usd: 1000,
        max_drawdown_pct: 5.0
    },
    market_data: {},
    selectedCoin: 'ETH',
    logs: [],
    closedTrades: [],
    totalPnl: 0,
    setRunning: (status) => set({ isRunning: status }),
    setSelectedCoin: (coin) => set({ selectedCoin: coin }),
    updateState: (data) => set((state) => ({
        ...state,
        ...data,
        walletBalance: data.walletBalance ?? state.walletBalance,
        positions: data.positions ?? state.positions,
        activeOrders: data.activeOrders ?? state.activeOrders,
        market_data: data.market_data ?? state.market_data,
        logs: data.logs ?? state.logs,
        closedTrades: data.closedTrades ?? state.closedTrades,
        totalPnl: data.totalPnl ?? state.totalPnl,
        config: data.config ? { ...state.config, ...data.config } : state.config
    })),
}));
