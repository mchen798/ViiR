import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Steps } from 'antd';
import * as api from '../api/mockService';

const stepNames = ['Trimmomatic', 'Trinity', 'RSEM', 'DESeq2', 'HMMER', 'BLASTN', 'Report'];

const TaskProgress: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState('PENDING');
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    const timer = setInterval(() => {
      if (id) {
        api.getTask(id).then((data) => {
          setStatus(data.status);
          setResult(data.result);
        });
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [id]);

  const currentStep = status === 'SUCCESS' ? stepNames.length : Math.min(stepNames.length - 1, 1);

  return (
    <Card title={`Task ${id}`}>
      <Steps direction="vertical" current={currentStep} items={stepNames.map((s) => ({ title: s }))} />
      <pre style={{ marginTop: 24 }}>{JSON.stringify(result, null, 2)}</pre>
    </Card>
  );
};

export default TaskProgress;
