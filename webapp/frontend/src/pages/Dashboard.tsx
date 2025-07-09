import React, { useEffect, useState } from 'react';
import { Typography, Button, Card, Table } from 'antd';
import { Link } from 'react-router-dom';
import DataChart from '../components/DataChart';
import * as api from '../api/mockService';
import { useTaskStore } from '../hooks/useTasks';

const { Title } = Typography;

interface ChartData {
  x: number[];
  y: number[];
}

const Dashboard: React.FC = () => {
  const [chart, setChart] = useState<ChartData>({ x: [], y: [] });
  const { tasks, fetchTasks } = useTaskStore();

  useEffect(() => {
    api.fetchChartData().then(setChart);
    fetchTasks();
  }, [fetchTasks]);

  const rows = Object.entries(tasks).map(([id, info]) => ({
    key: id,
    id,
    status: info.status,
    result: info.result,
  }));

  const columns = [
    { title: 'Task ID', dataIndex: 'id' },
    { title: 'Status', dataIndex: 'status' },
    { title: 'Result', dataIndex: 'result' },
  ];

  return (
    <div>
      <Title level={2}>Welcome to ViiR RNA Virus Detection System</Title>
      <Button type="primary" style={{ marginBottom: 16 }}>
        <Link to="/new">Start New Task</Link>
      </Button>
      <Card style={{ marginBottom: 24 }}>
        <DataChart data={chart} />
      </Card>
      <Card>
        <Table dataSource={rows} columns={columns} pagination={false} />
      </Card>
    </div>
  );
};

export default Dashboard;
