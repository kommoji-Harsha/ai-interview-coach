"use client";

import React from "react";

export interface RadarDimension {
  label: string;
  score: number; // 0 to 5
}

interface RadarChartProps {
  dimensions: RadarDimension[];
  maxScore?: number;
  size?: number;
}

export function RadarChart({
  dimensions,
  maxScore = 5,
  size = 280,
}: RadarChartProps): React.ReactElement {
  const validDimensions =
    dimensions.length >= 3
      ? dimensions
      : [
          ...dimensions,
          ...Array.from(
            { length: Math.max(0, 3 - dimensions.length) },
            (_, idx) => ({
              label: `Dimension ${dimensions.length + idx + 1}`,
              score: 0,
            })
          ),
        ];

  const center = size / 2;
  const radius = size * 0.34;
  const count = validDimensions.length;
  const levels = [1, 2, 3, 4, 5];

  const getCoordinates = (index: number, value: number) => {
    const angle = (Math.PI * 2 * index) / count - Math.PI / 2;
    const r = (Math.max(0, Math.min(value, maxScore)) / maxScore) * radius;
    return {
      x: center + r * Math.cos(angle),
      y: center + r * Math.sin(angle),
    };
  };

  const dataPoints = validDimensions.map((dim, i) =>
    getCoordinates(i, dim.score)
  );
  const polygonPoints = dataPoints.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <div className="flex flex-col items-center">
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label="Rubric Dimension Radar Chart"
        className="max-w-[300px] overflow-visible"
      >
        <title>Rubric Scores Radar Chart</title>
        <desc>
          {validDimensions
            .map((d) => `${d.label}: ${d.score.toFixed(1)} out of ${maxScore}`)
            .join(", ")}
        </desc>

        {/* Concentric grid polygons */}
        {levels.map((level) => {
          const levelPoints = validDimensions
            .map((_, i) => {
              const p = getCoordinates(i, level);
              return `${p.x},${p.y}`;
            })
            .join(" ");
          return (
            <polygon
              key={level}
              points={levelPoints}
              fill="none"
              stroke="#e2e8f0"
              strokeWidth="1"
            />
          );
        })}

        {/* Axis lines and labels */}
        {validDimensions.map((dim, i) => {
          const end = getCoordinates(i, maxScore);
          const labelPos = getCoordinates(i, maxScore * 1.24);
          return (
            <g key={dim.label}>
              <line
                x1={center}
                y1={center}
                x2={end.x}
                y2={end.y}
                stroke="#cbd5e1"
                strokeWidth="1"
              />
              <text
                x={labelPos.x}
                y={labelPos.y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-slate-700 text-[11px] font-medium capitalize"
              >
                {dim.label.replace(/_/g, " ")} ({dim.score.toFixed(1)})
              </text>
            </g>
          );
        })}

        {/* Data polygon */}
        <polygon
          points={polygonPoints}
          fill="rgba(79, 70, 229, 0.22)"
          stroke="#4f46e5"
          strokeWidth="2.5"
        />

        {/* Data vertices */}
        {dataPoints.map((p, i) => (
          <circle
            key={validDimensions[i].label}
            cx={p.x}
            cy={p.y}
            r="4"
            fill="#4f46e5"
          />
        ))}
      </svg>

      {/* Screen-reader accessible summary list */}
      <ul className="sr-only" aria-label="Rubric dimension scores list">
        {dimensions.map((d) => (
          <li key={d.label}>
            {d.label.replace(/_/g, " ")}: {d.score.toFixed(1)} / {maxScore}
          </li>
        ))}
      </ul>
    </div>
  );
}
