import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { BarChartBlock as BarChartBlockType } from '../../../types/chat';
import { CHART_COLORS, AXIS_STYLE, GRID_STYLE, TOOLTIP_STYLE, CONTAINER_STYLE, TITLE_STYLE } from './chart-theme';

export function BarChartBlockView({ block }: { block: BarChartBlockType }) {
  // Bound to a local so narrowing survives into the closure below: `series`
  // is optional now that a block may instead carry a `series_ref`.
  const series = block.series;
  if (!series || series.length === 0) return null;

  const chartData = series[0].data.map((point, i) => {
    const row: Record<string, any> = { [block.x_label || 'x']: point.x };
    series.forEach(s => {
      row[s.name] = s.data[i]?.y ?? null;
    });
    return row;
  });

  return (
    <div style={CONTAINER_STYLE}>
      <p style={TITLE_STYLE}>{block.title}</p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid {...GRID_STYLE} vertical={false} />
          <XAxis dataKey={block.x_label || 'x'} tick={AXIS_STYLE} axisLine={false} tickLine={false} dy={10} />
          <YAxis tick={AXIS_STYLE} axisLine={false} tickLine={false} dx={-10} />
          <Tooltip 
            contentStyle={TOOLTIP_STYLE}
            itemStyle={{ fontFamily: 'DM Sans', fontSize: '13px' }}
            labelStyle={{ color: 'rgba(255,255,255,0.7)', marginBottom: '8px', fontFamily: 'DM Sans', fontSize: '12px' }}
            cursor={{ fill: 'rgba(26,43,26,0.05)' }}
          />
          {series.length > 1 && (
            <Legend wrapperStyle={{ paddingTop: '20px', fontSize: '12px', fontFamily: 'DM Sans', color: '#4A6741' }} />
          )}

          {series.map((s, index) => (
            <Bar
              key={s.name}
              dataKey={s.name}
              fill={s.color || CHART_COLORS[index % CHART_COLORS.length]}
              radius={[4, 4, 0, 0]}
              maxBarSize={48}
              isAnimationActive={true}
              animationDuration={800}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
