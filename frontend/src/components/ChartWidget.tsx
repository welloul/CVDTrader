import React, { useEffect, useRef } from 'react';
import * as LightweightCharts from 'lightweight-charts';
import { useStore } from '../store/useStore';

const ChartWidget: React.FC = () => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<LightweightCharts.IChartApi | null>(null);
    const candlestickSeriesRef = useRef<LightweightCharts.ISeriesApi<'Candlestick'> | null>(null);
    const cvdSeriesRef = useRef<LightweightCharts.ISeriesApi<'Histogram'> | null>(null);
    const pocSeriesRef = useRef<LightweightCharts.ISeriesApi<'Line'> | null>(null);

    const selectedCoin = useStore(state => state.selectedCoin);
    const marketData = useStore(state => state.market_data[selectedCoin]);

    useEffect(() => {
        const container = chartContainerRef.current;
        if (!container) return;

        if (chartRef.current) {
            chartRef.current.remove();
        }

        const chart = LightweightCharts.createChart(container, {
            layout: {
                background: { color: 'transparent' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: 'rgba(42, 46, 57, 0.1)' },
                horzLines: { color: 'rgba(42, 46, 57, 0.1)' },
            },
            timeScale: {
                timeVisible: true,
            },
            width: container.clientWidth,
            height: container.clientHeight || 400,
        });

        chartRef.current = chart;

        const candlestickSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#2ebd85',
            downColor: '#e0294a',
            borderVisible: false,
            wickUpColor: '#2ebd85',
            wickDownColor: '#e0294a',
        });
        candlestickSeriesRef.current = candlestickSeries;

        const cvdSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
            color: '#26a69a',
            priceFormat: { type: 'volume' },
            priceScaleId: 'cvd',
        });
        cvdSeriesRef.current = cvdSeries;

        chart.priceScale('cvd').applyOptions({
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });

        // POC per-candle line series (step-line so each candle's POC is visible as a horizontal tick)
        const pocSeries = chart.addSeries(LightweightCharts.LineSeries, {
            color: '#fcd34d',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.LargeDashed,
            crosshairMarkerVisible: false,
            lastValueVisible: true,
            priceLineVisible: false,
            title: 'POC',
            lineType: LightweightCharts.LineType.WithSteps,
        });
        pocSeriesRef.current = pocSeries;

        const handleResize = () => {
            if (container && chartRef.current) {
                chartRef.current.applyOptions({
                    width: container.clientWidth,
                    height: container.clientHeight,
                });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (chartRef.current) {
                chartRef.current.remove();
                chartRef.current = null;
            }
        };
    }, [selectedCoin]);

    useEffect(() => {
        if (!marketData || !candlestickSeriesRef.current || !cvdSeriesRef.current) return;

        const candles = marketData.candles || [];
        if (candles.length === 0) return;

        // Dedup and sort to prevent Lightweight Charts crash
        // candles[].time is in SECONDS already
        const uniqueCandles = Array.from(new Map(candles.map((c: any) => [c.time, c])).values())
            .sort((a: any, b: any) => a.time - b.time);

        const formattedCandles = uniqueCandles.map((c: any) => ({
            time: c.time as any,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close
        }));

        const formattedCvd = uniqueCandles.map((c: any) => ({
            time: c.time as any,
            value: c.cvd,
            color: c.cvd >= 0 ? '#26a69a' : '#ef5350'
        }));

        candlestickSeriesRef.current.setData(formattedCandles);
        cvdSeriesRef.current.setData(formattedCvd);

        // Per-candle POC overlay as a step line
        if (pocSeriesRef.current) {
            const formattedPoc = uniqueCandles
                .filter((c: any) => c.poc != null)
                .map((c: any) => ({
                    time: c.time as any,
                    value: c.poc,
                }));
            pocSeriesRef.current.setData(formattedPoc);
        }


    }, [marketData]);

    return (
        <div className="w-full h-full relative min-h-[400px]" ref={chartContainerRef}>
            <div className="absolute top-4 left-4 z-10 text-xl font-bold text-gray-200 pointer-events-none drop-shadow-md flex items-center gap-2">
                {selectedCoin}-PERP <span className="text-[10px] text-gray-500 font-mono italic">v1.1-fixed</span>
                <span className="text-sm font-normal text-gray-400">Hyperliquid</span>
                {marketData?.price && (
                    <span className="ml-4 text-accent font-mono">${marketData.price.toLocaleString()}</span>
                )}
            </div>
        </div>
    );
};

export default ChartWidget;
