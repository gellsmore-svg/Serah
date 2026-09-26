import { useMemo, useState, type MouseEvent } from "react";
import type { SeriesPoint } from "./api";
import { formatIntensity, formatWhen } from "./format";

export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  points: SeriesPoint[];
}

interface Props {
  series: ChartSeries[];
  mode: "raw" | "reservoir";
  showDensity: boolean;
  onSelect: (point: SeriesPoint, seriesId: string) => void;
}

const WIDTH = 860;
const HEIGHT = 420;
const PAD = { left: 48, right: 20, top: 18, bottom: 36 };

export function Chart({ series, mode, showDensity, onSelect }: Props) {
  const [hover, setHover] = useState<{ series: ChartSeries; point: SeriesPoint; x: number; y: number } | null>(null);
  const layout = useMemo(() => layoutSeries(series), [series]);

  function locate(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * WIDTH;
    let best: { series: ChartSeries; point: SeriesPoint; x: number; y: number; distance: number } | null = null;
    for (const line of layout) {
      for (const placed of line.placed) {
        const distance = Math.abs(placed.x - x);
        if (best === null || distance < best.distance) {
          best = { series: line.series, point: placed.point, x: placed.x, y: placed.y, distance };
        }
      }
    }
    if (best && best.distance < 28) {
      setHover(best);
    } else {
      setHover(null);
    }
  }

  return (
    <div className="chart-wrap">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Intensity over time"
        onMouseMove={locate}
        onMouseLeave={() => setHover(null)}
        onClick={() => {
          if (hover) {
            onSelect(hover.point, hover.series.id);
          }
        }}
      >
        {[0, 25, 50, 75, 100].map((tick) => {
          const y = yFor(tick);
          return (
            <g key={tick}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y} className="grid" />
              <text x={PAD.left - 8} y={y + 4} className="tick" textAnchor="end">
                {tick}
              </text>
            </g>
          );
        })}
        {showDensity && mode === "reservoir" && layout[0] && (
          <g>
            {layout[0].placed.map((placed) => (
              <rect
                key={placed.point.t}
                x={placed.x - 6}
                y={HEIGHT - PAD.bottom - Math.min(48, (placed.point.evidence_episodes ?? 0) * 10)}
                width={12}
                height={Math.min(48, (placed.point.evidence_episodes ?? 0) * 10)}
                className="density"
              />
            ))}
          </g>
        )}
        {layout.map((line) => (
          <g key={line.series.id}>
            <polyline points={line.placed.map((item) => `${item.x},${item.y}`).join(" ")} fill="none" stroke={line.series.color} strokeWidth={mode === "raw" ? 1.4 : 2.2} />
            {line.placed.map((placed) => (
              <circle
                key={`${line.series.id}-${placed.point.t}`}
                cx={placed.x}
                cy={placed.y}
                r={placed.point.observed === false ? 3.2 : 4.2}
                fill={placed.point.observed === false ? "#faf7f2" : line.series.color}
                stroke={line.series.color}
                strokeWidth={1.6}
              />
            ))}
          </g>
        ))}
        {hover && (
          <line x1={hover.x} x2={hover.x} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="hover-line" />
        )}
      </svg>
      {hover && (
        <div className="tooltip">
          <strong>{hover.series.label}</strong>
          <span>{formatWhen(hover.point.t)}</span>
          <span>Derived intensity {formatIntensity(hover.point.level)}</span>
          {mode === "reservoir" && (
            <span>{hover.point.observed ? "Observation recorded" : "No observation — decay only"}</span>
          )}
          {mode === "raw" && <span>Raw observation</span>}
          {hover.point.concentration != null && (
            <span>Distribution concentration {hover.point.concentration.toFixed(2)}</span>
          )}
          {hover.point.concept_version != null && <span>Concept version {hover.point.concept_version}</span>}
        </div>
      )}
      <ul className="legend">
        {series.map((line) => (
          <li key={line.id}>
            <i style={{ background: line.color }} />
            {line.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function yFor(level: number): number {
  const span = HEIGHT - PAD.top - PAD.bottom;
  return PAD.top + ((100 - level) / 100) * span;
}

function layoutSeries(series: ChartSeries[]) {
  const times = series.flatMap((line) => line.points.map((point) => Date.parse(point.t.length === 10 ? `${point.t}T00:00:00Z` : point.t)));
  const min = times.length ? Math.min(...times) : 0;
  const max = times.length ? Math.max(...times) : 1;
  const span = Math.max(1, max - min);
  return series.map((line) => ({
    series: line,
    placed: line.points
      .filter((point) => point.level != null)
      .map((point) => {
        const time = Date.parse(point.t.length === 10 ? `${point.t}T00:00:00Z` : point.t);
        const x = PAD.left + ((time - min) / span) * (WIDTH - PAD.left - PAD.right);
        return { point, x, y: yFor(point.level ?? 0) };
      }),
  }));
}
