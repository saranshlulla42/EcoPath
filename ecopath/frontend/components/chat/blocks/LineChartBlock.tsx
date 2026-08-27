import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import { LineChartBlock as LineChartBlockType } from '../../../types/chat';
import { CHART_COLORS, AXIS_STYLE, GRID_STYLE, TOOLTIP_STYLE, CONTAINER_STYLE, TITLE_STYLE } from './chart-theme';

export function LineChartBlockView({ block }: { block: LineChartBlockType }) {
  if (!block.series || block.series.length === 0) return null;

  const chartData = block.series[0].data.map((point, i) => {
    const row: Record<string, any> = { [block.x_label || 'x']: point.x };
    block.series.forEach(s => {
      row[s.name] = s.data[i]?.y ?? null;
    });
    return row;
  });

  return (
    <div style={CONTAINER_STYLE}>
      <p style={TITLE_STYLE}>{block.title}</p>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid {...GRID_STYLE} vertical={false} />
          <XAxis dataKey={block.x_label || 'x'} tick={AXIS_STYLE} axisLine={false} tickLine={false} dy={10} />
          <YAxis tick={AXIS_STYLE} axisLine={false} tickLine={false} dx={-10} />
          <Tooltip 
            contentStyle={TOOLTIP_STYLE}
            itemStyle={{ fontFamily: 'DM Sans', fontSize: '13px' }}
            labelStyle={{ color: 'rgba(255,255,255,0.7)', marginBottom: '8px', fontFamily: 'DM Sans', fontSize: '12px' }}
            cursor={{ stroke: '#D1DDD0' }}
          />
          {block.series.length > 1 && (
            <Legend wrapperStyle={{ paddingTop: '20px', fontSize: '12px', fontFamily: 'DM Sans', color: '#4A6741' }} />
          )}

          {block.annotations?.map(ann => (
            <ReferenceLine
              key={ann.x}
              x={ann.x}
              stroke="#7A9876"
              strokeDasharray="4 4"
              label={{
                value: ann.label,
                position: 'top',
                fill: '#4A6741',
                fontSize: 10,
                fontFamily: 'DM Sans'
              }}
            />
          ))}

          {block.series.map((s, index) => (
            <Line
              key={s.name}
              type="monotone"
              dataKey={s.name}
              stroke={s.color || CHART_COLORS[index % CHART_COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
              isAnimationActive={true}
              animationDuration={1200}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
