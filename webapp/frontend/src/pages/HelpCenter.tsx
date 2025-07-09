import React from 'react';
import { Card, Typography } from 'antd';

const { Title, Paragraph } = Typography;

const HelpCenter: React.FC = () => (
  <Card>
    <Title level={2}>Help Center</Title>
    <Paragraph>For assistance, please contact support@viir.example.com.</Paragraph>
  </Card>
);

export default HelpCenter;
