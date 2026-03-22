// src/components/charts/VitalsChart.tsx
// Real-time line chart using Chart.js for ICU vitals time series

import React, { useEffect, useRef } from 'react';
import {
  Chart, ChartConfiguration, LineController, LineElement,
  PointElement, LinearScale, TimeScale, Filler, Tooltip, Legend,
} from 'chart.js';
import 'chartjs-adapter-date-fns';
import { VitalRecord } from '../../types';

Chart.register(
  LineController, LineElement, PointElement, LinearScale,
  TimeScale, Filler, Tooltip, Legend
);

interface Dataset {
  label:       string;
  key:         keyof VitalRecord;
  color:       string;
  yMin?:       number;
  yMax?:       number;
  hidden?:     boolean;
}

const DATASETS: Dataset[] = [
  { label: 'Heart Rate (bpm)',   key: 'heartRate',       color: '#ef4444'  },
  { label: 'SpO2 (%)',           key: 'spo2',            color: '#3b82f6'  },
  { label: 'Systolic BP (mmHg)', key: 'systolicBp',      color: '#f59e0b'  },
  { label: 'Resp. Rate (br/m)', key: 'respiratoryRate', color: '#22c55e', hidden: true },
  { label: 'Temp (°C)',          key: 'temperature',     color: '#a855f7', hidden: true },
  { label: 'Lactate (mmol/L)',   key: 'lactate',         color: '#ec4899', hidden: true },
];

interface Props {
  records:   VitalRecord[];
  patientId: string;
  height?:   number;
}

export const VitalsChart: React.FC<Props> = ({ records, patientId, height = 280 }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef  = useRef<Chart | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const ctx = canvasRef.current.getContext('2d')!;

    const labels = records.map(r => new Date(r.timestamp));

    const chartConfig: ChartConfiguration = {
      type: 'line',
      data: {
        labels,
        datasets: DATASETS.map(ds => ({
          label:           ds.label,
          data:            records.map(r => r[ds.key] as number),
          borderColor:     ds.color,
          backgroundColor: ds.color + '18',
          pointRadius:     records.length > 100 ? 0 : 2,
          pointHoverRadius: 4,
          borderWidth:     2,
          fill:            false,
          tension:         0.3,
          hidden:          ds.hidden ?? false,
        })),
      },
      options: {
        responsive:          true,
        maintainAspectRatio: false,
        animation:           { duration: 200 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position:  'bottom',
            labels: {
              color:      '#9ca3af',
              font:       { size: 11 },
              boxWidth:   12,
              padding:    12,
            },
          },
          tooltip: {
            backgroundColor: 'rgba(17,24,39,0.95)',
            titleColor:      '#f9fafb',
            bodyColor:       '#d1d5db',
            borderColor:     '#374151',
            borderWidth:     1,
            padding:         10,
          },
        },
        scales: {
          x: {
            type:   'time',
            time:   { unit: 'minute', displayFormats: { minute: 'HH:mm' } },
            grid:   { color: 'rgba(255,255,255,0.04)' },
            ticks:  { color: '#6b7280', maxTicksLimit: 8, font: { size: 11 } },
          },
          y: {
            grid:   { color: 'rgba(255,255,255,0.04)' },
            ticks:  { color: '#6b7280', font: { size: 11 } },
          },
        },
      },
    };

    chartRef.current = new Chart(ctx, chartConfig);

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  // Live update without full re-render
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || records.length === 0) return;

    chart.data.labels = records.map(r => new Date(r.timestamp));
    DATASETS.forEach((ds, idx) => {
      chart.data.datasets[idx].data = records.map(r => r[ds.key] as number);
    });
    chart.update('none'); // no animation for real-time updates
  }, [records]);

  return (
    <div style={{ position: 'relative', height, width: '100%' }}>
      <canvas ref={canvasRef} />
    </div>
  );
};
