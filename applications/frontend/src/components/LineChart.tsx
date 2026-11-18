import type { MetricPoint } from "../lib/api";
import { formatShortTime } from "../lib/format";

interface LineChartProps {
  title: string;
  unit: string;
  points: MetricPoint[];
  /** Formats the current value shown in the header. */
  formatValue?: (value: number) => string;
  color?: string;
  height?: number;
}

const WIDTH = 640;
const PAD = { top: 18, right: 14, bottom: 26, left: 46 };

/**
 * Hand-written SVG line chart (no chart library). Renders only the points the
 * API returned; an empty series shows a "no samples" note instead of a fake line.
 */
export function LineChart({ title, unit, points, formatValue, color = "var(--accent)", height = 190 }: LineChartProps) {
  const format = formatValue ?? ((value: number) => `${value}`);
  const hasData = points.length > 0;
  const values = points.map((point) => point.v);
  const rawMin = hasData ? Math.min(...values) : 0;
  const rawMax = hasData ? Math.max(...values) : 1;
  const span = rawMax - rawMin || Math.max(Math.abs(rawMax), 1) * 0.2;
  const yMin = rawMin - span * 0.15;
  const yMax = rawMax + span * 0.15;
  const innerWidth = WIDTH - PAD.left - PAD.right;
  const innerHeight = height - PAD.top - PAD.bottom;

  const xFor = (index: number) =>
    PAD.left + (points.length <= 1 ? innerWidth / 2 : (index / (points.length - 1)) * innerWidth);
  const yFor = (value: number) =>
    PAD.top + innerHeight - ((value - yMin) / (yMax - yMin)) * innerHeight;

  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(2)},${yFor(point.v).toFixed(2)}`).join(" ");
  const areaPath = hasData
    ? `${linePath} L${xFor(points.length - 1).toFixed(2)},${(PAD.top + innerHeight).toFixed(2)} L${xFor(0).toFixed(2)},${(PAD.top + innerHeight).toFixed(2)} Z`
    : "";

  const gridLines = [0, 0.25, 0.5, 0.75, 1];
  const last = points[points.length - 1];
  const first = points[0];
  const gradientId = `chart-${title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;

  return (
    <figure className="chart">
      <figcaption className="chart__head">
        <span className="chart__title">{title}</span>
        <span className="chart__meta">
          {last ? (
            <>
              <strong>{format(last.v)}</strong> <span className="chart__unit">{unit}</span>
            </>
          ) : (
            "no samples"
          )}
        </span>
      </figcaption>
      {hasData ? (
        <svg
          className="chart__svg"
          viewBox={`0 0 ${WIDTH} ${height}`}
          role="img"
          aria-label={`${title} time series, ${points.length} samples, latest ${format(last.v)} ${unit}`}
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.28" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          {gridLines.map((ratio) => {
            const y = PAD.top + innerHeight * ratio;
            const value = yMax - (yMax - yMin) * ratio;
            return (
              <g key={ratio}>
                <line
                  x1={PAD.left}
                  x2={WIDTH - PAD.right}
                  y1={y}
                  y2={y}
                  stroke="var(--border)"
                  strokeDasharray="3 5"
                />
                <text x={PAD.left - 8} y={y + 4} textAnchor="end" className="chart__axis-label">
                  {value.toFixed(value >= 10 ? 0 : 2)}
                </text>
              </g>
            );
          })}
          <path d={areaPath} fill={`url(#${gradientId})`} />
          <path d={linePath} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {last ? <circle cx={xFor(points.length - 1)} cy={yFor(last.v)} r="3.5" fill={color} /> : null}
          {first ? (
            <text x={PAD.left} y={height - 6} className="chart__axis-label">
              {formatShortTime(first.t)}
            </text>
          ) : null}
          {last ? (
            <text x={WIDTH - PAD.right} y={height - 6} textAnchor="end" className="chart__axis-label">
              {formatShortTime(last.t)}
            </text>
          ) : null}
        </svg>
      ) : (
        <p className="chart__empty">No samples returned for this series.</p>
      )}
    </figure>
  );
}
