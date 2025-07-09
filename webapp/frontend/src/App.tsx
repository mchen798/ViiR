import React from 'react';
import { Layout } from 'antd';
import { Route, Routes } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import NewTask from './pages/NewTask';
import TaskList from './pages/TaskList';
import TaskProgress from './pages/TaskProgress';
import HelpCenter from './pages/HelpCenter';

const { Content } = Layout;

const App: React.FC = () => (
  <Layout style={{ minHeight: '100vh' }}>
    <Navbar />
    <Content style={{ padding: '2rem' }}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/new" element={<NewTask />} />
        <Route path="/tasks" element={<TaskList />} />
        <Route path="/tasks/:id" element={<TaskProgress />} />
        <Route path="/help" element={<HelpCenter />} />
      </Routes>
    </Content>
  </Layout>
);

export default App;
