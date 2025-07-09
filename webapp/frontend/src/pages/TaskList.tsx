import React, { useEffect } from 'react';
import { Table, Button } from 'antd';
import { Link } from 'react-router-dom';
import { useTaskStore } from '../hooks/useTasks';

const TaskList: React.FC = () => {
  const { tasks, fetchTasks } = useTaskStore();

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const data = Object.entries(tasks).map(([id, info]) => ({ key: id, id, ...info }));

  const columns = [
    { title: 'Task ID', dataIndex: 'id' },
    { title: 'Status', dataIndex: 'status' },
    { title: 'Result', dataIndex: 'result' },
    {
      title: 'Action',
      render: (_: any, record: any) => (
        <Button type="link">
          <Link to={`/tasks/${record.id}`}>View</Link>
        </Button>
      ),
    },
  ];

  return <Table dataSource={data} columns={columns} />;
};

export default TaskList;
