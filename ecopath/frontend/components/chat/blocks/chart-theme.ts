export const CHART_COLORS = ['#2D7D52', '#3A9E7A', '#5BB89A', '#D4880A', '#7A6FB0', '#B5602A'];
export const AXIS_STYLE = { fontSize: 11, fill: '#7A9876', fontFamily: 'DM Sans' };
export const GRID_STYLE = { strokeDasharray: '3 3', stroke: '#E2EAE1' };
// This tooltip is a floating box drawn over the chart, not the page background,
// so it deliberately stays dark with light text for its own contrast.
export const TOOLTIP_STYLE = { backgroundColor: 'rgba(28,43,32,0.94)', border: 'none', borderRadius: '8px' };
export const CONTAINER_STYLE = {
  border: '1px solid #D1DDD0',
  borderRadius: '12px',
  padding: '20px 16px 12px 8px',
  background: '#FFFFFF',
  marginTop: '16px',
  boxShadow: '0 1px 3px rgba(26, 43, 26, 0.08), 0 1px 2px rgba(26, 43, 26, 0.04)',
};
export const TITLE_STYLE = {
  fontFamily: 'DM Sans',
  fontSize: '13px',
  fontWeight: 600,
  color: '#4A6741',
  marginBottom: '12px',
  marginLeft: '12px',
};
