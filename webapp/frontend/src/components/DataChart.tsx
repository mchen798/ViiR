import React from 'react';
import Plot from 'react-plotly.js';

interface Props {
  data: { x: number[]; y: number[] };
}

const DataChart: React.FC<Props> = ({ data }) => (
  <Plot
    data={[{ x: data.x, y: data.y, type: 'scatter', mode: 'lines+markers' }]}
    layout={{ title: 'Sample Data' }}
    style={{ width: '100%', height: '400px' }}
  />
);

export default DataChart;
