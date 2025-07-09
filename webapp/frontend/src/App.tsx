import React, { useEffect, useState } from 'react';
import { Layout, Button } from 'antd';
import axios from 'axios';
import DataChart from './components/DataChart';

interface ChartData {
  x: number[];
  y: number[];
}

const { Header, Content } = Layout;

function App() {
  const [data, setData] = useState<ChartData>({ x: [], y: [] });

  useEffect(() => {
    axios.get('/data').then(res => setData(res.data));
  }, []);

  const triggerTask = () => {
    axios.post('/process');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ color: 'white' }}>ViiR Dashboard</Header>
      <Content style={{ padding: '2rem' }}>
        <Button type="primary" onClick={triggerTask}>Run Background Task</Button>
        <DataChart data={data} />
      </Content>
    </Layout>
  );
}

export default App;
