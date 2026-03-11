import React, { useEffect, useRef } from 'react';
import * as LightweightCharts from 'lightweight-charts';
import { useStore } from '../store/useStore';

const CandleHistory: React.FC = () => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<LightweightCharts.IChartApi | null>(null);
    const priceSeriesRef = useRef<LightweightCharts.ISeriesApi<"Area"> | null>(null);
    const cvdSeriesRef = useRef<LightweightCharts.ISeriesApi<"Histogram"> | null>(null);
    const pocSeriesRef = useRef<LightweightCharts.ISeriesApi<"Line"> | null>(null);

    const selectedCoin = useStore(state => state.selectedCoin);
    const marketData = useStore(state => state.market_data[selectedCoin]);
    const candles = marketData?.candles || [];

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Cleanup previous chart
        if (chartRef.current) {
            chartRef.current.remove();
        }

        const chart = LightweightCharts.createChart(chartContainerRef.current, {
            layout: {
                background: { type: LightweightCharts.ColorType.Solid, color: 'transparent' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: '#1e222d' },
                horzLines: { color: '#1e222d' },
            },
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // v5 API: Use addSeries with the series definition
        const priceSeries = chart.addSeries(LightweightCharts.AreaSeries, {
            topColor: 'rgba(33, 150, 243, 0.4)',
            bottomColor: 'rgba(33, 150, 243, 0.0)',
            lineColor: '#2196f3',
            lineWidth: 2,
            priceFormat: { type: 'price', precision: 2, minMove: 0.1 },
            title: 'Close',
        });

        const pocSeries = chart.addSeries(LightweightCharts.LineSeries, {
            color: '#facc15',
            lineWidth: 2,
            lineStyle: 2, // Dashed
            title: 'POC',
        });

        const cvdSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
            color: '#26a69a',
            priceFormat: { type: 'volume' },
            priceScaleId: 'cvd',
            title: 'CVD',
        });

        chart.priceScale('cvd').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        chartRef.current = chart;
        priceSeriesRef.current = priceSeries;
        pocSeriesRef.current = pocSeries;
        cvdSeriesRef.current = cvdSeries;

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
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
        if (!chartRef.current || !priceSeriesRef.current || !cvdSeriesRef.current || !pocSeriesRef.current) return;

        if (candles.length > 0) {
            // Dedup and sort
            // candles[].time is in SECONDS already
            const uniqueCandles = Array.from(new Map(candles.map((c: any) => [c.time, c])).values())
                .sort((a: any, b: any) => a.time - b.time);

            const priceData = uniqueCandles.map((c: any) => ({
                time: c.time as any,
                value: c.close
            }));

            const pocData = uniqueCandles.map((c: any) => ({
                time: c.time as any,
                value: c.poc || c.close
            }));

            const cvdData = uniqueCandles.map((c: any) => ({
                time: c.time as any,
                value: c.cvd,
                color: c.cvd >= 0 ? '#2ebd85' : '#f6465d'
            }));

            priceSeriesRef.current.setData(priceData);
            pocSeriesRef.current.setData(pocData);
            cvdSeriesRef.current.setData(cvdData);

            chartRef.current.timeScale().fitContent();
        }
    }, [candles, selectedCoin]);

    return (
        <div className="h-full flex flex-col relative">
            <div className="flex justify-between items-center mb-2 pb-2 border-b border-gray-800">
                <h3 className="font-semibold text-gray-300">CVD & POC Verification</h3>
                <span className="text-xs text-yellow-500 font-mono">Dashed = POC</span>
            </div>
            <div ref={chartContainerRef} className="flex-1 w-full" />
            {candles.length === 0 && (
                <div className="absolute inset-x-0 bottom-12 text-gray-600 text-sm italic text-center">
                    Waiting for 1m closed candles...
                </div>
            )}
        </div>
    );
};

export default CandleHistory;
