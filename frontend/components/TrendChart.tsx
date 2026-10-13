"use client";

import React from "react";
import { ScoreTrendPoint } from "@/lib/types";

interface TrendChartProps {
  data: ScoreTrendPoint[];
  maxScore?: number;
}

export function TrendChart({
  data,
  maxScore = 5,
}: TrendChartProps): React.ReactElement {
  if (data.length === 0) {
    return (
      <p className="text-sm text-slate-500">No score trend points available.</p>
    );
  }

  const width = 560;
  const height = 220;
  const padLeft = 40;
  const padRight = 24;
  const padTop = 20;
  const padBottom = 36;
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;

  const points = data.map((point, index) => {
    const x =
      data.length === 1
        ? padLeft + innerW / 2
        : padLeft + (index / (data.length - 1)) * innerW;
    const clamped = Math.max(0, Math.min(point.overall, maxScore));
    const y = padTop + innerH - (clamped / maxScore) * innerH;
    return { ...point, x, y };
  });

  const polylinePoints = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Overall Score Trend Over Time"
        className="h-auto w-full min-w-[320px]"
      >
        <title>Score Trend Chart</title>
        <desc>
          {data
            .map((d) => `${d.date}: ${d.overall.toFixed(1)} / ${maxScore}`)
            .join(", ")}
        </desc>

        {/* Horizontal grid lines */}
        {[1, 2, 3, 4, 5].map((tick) => {
          const y = padTop + innerH - (tick / maxScore) * innerH;
          return (
            <g key={tick}>
              <line
                x1={padLeft}
                y1={y}
                x2={width - padRight}
                y2={y}
                stroke="#e2e8f0"
                strokeDasharray="3 3"
              />
              <text
                x={padLeft - 8}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-slate-500 text-[11px]"
              >
                {tick}.0
              </text>
            </g>
          );
        })}

        {/* Line path */}
        {points.length > 1 && (
          <polyline
            fill="none"
            stroke="#4f46e5"
            strokeWidth="2.5"
            points={polylinePoints}
          />
        )}

        {/* Data points & X-axis labels */}
        {points.map((p) => (
          <g key={`${p.date}-${p.x}`}>
            <circle cx={p.x} cy={p.y} r="4.5" fill="#4f46e5" />
            <text
              x={p.x}
              y={p.y - 10}
              textAnchor="middle"
              className="fill-indigo-700 text-[11px] font-semibold"
            >
              {p.overall.toFixed(1)}
            </text>
            <text
              x={p.x}
              y={height - 10}
              textAnchor="middle"
              className="fill-slate-600 text-[10px]"
            >
              {p.date}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
