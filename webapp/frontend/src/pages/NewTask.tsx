import React, { useState } from 'react';
import { Steps, Button, Form, Input, Upload, message, Card } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import * as api from '../api/mockService';

const { Dragger } = Upload;

const stepTitles = [
  'Project Info',
  'Data Upload',
  'Parameter Setting',
  'Validation',
  'Submit',
];

const NewTask: React.FC = () => {
  const [current, setCurrent] = useState(0);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const next = () => setCurrent(current + 1);
  const prev = () => setCurrent(current - 1);

  const submit = async () => {
    await api.createTask(form.getFieldsValue());
    message.success('Task submitted');
    navigate('/tasks');
  };

  const renderStep = () => {
    switch (current) {
      case 0:
        return (
          <Form form={form} layout="vertical">
            <Form.Item name="project" label="Project Name" rules={[{ required: true }]}> 
              <Input placeholder="Enter project name" />
            </Form.Item>
          </Form>
        );
      case 1:
        return (
          <Dragger name="file" multiple={false} action="/" beforeUpload={() => false}>
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">Click or drag FASTQ file here</p>
          </Dragger>
        );
      case 2:
        return (
          <Form form={form} layout="vertical">
            <Form.Item name="param" label="Parameter">
              <Input placeholder="Parameter value" />
            </Form.Item>
          </Form>
        );
      case 3:
        return <p>Validate your inputs before submitting.</p>;
      case 4:
        return <p>Ready to submit.</p>;
      default:
        return null;
    }
  };

  return (
    <Card>
      <Steps current={current} items={stepTitles.map((t) => ({ title: t }))} />
      <div style={{ marginTop: 24 }}>{renderStep()}</div>
      <div style={{ marginTop: 24 }}>
        {current > 0 && (
          <Button onClick={prev} style={{ marginRight: 8 }}>
            Back
          </Button>
        )}
        {current < stepTitles.length - 1 && (
          <Button type="primary" onClick={next}>
            Next
          </Button>
        )}
        {current === stepTitles.length - 1 && (
          <Button type="primary" onClick={submit}>
            Submit
          </Button>
        )}
      </div>
    </Card>
  );
};

export default NewTask;
