import React from 'react';
import { Layout, Menu } from 'antd';
import { Link, useLocation } from 'react-router-dom';

const { Header } = Layout;

const Navbar: React.FC = () => {
  const location = useLocation();
  return (
    <Header>
      <div style={{ float: 'left', color: '#fff', marginRight: '1rem' }}>
        ViiR Viral Detection
      </div>
      <Menu
        theme="dark"
        mode="horizontal"
        selectedKeys={[location.pathname]}
        style={{ lineHeight: '64px' }}
      >
        <Menu.Item key="/">
          <Link to="/">Dashboard</Link>
        </Menu.Item>
        <Menu.Item key="/new">
          <Link to="/new">Create Task</Link>
        </Menu.Item>
        <Menu.Item key="/tasks">
          <Link to="/tasks">Task List</Link>
        </Menu.Item>
        <Menu.Item key="/help">
          <Link to="/help">Help</Link>
        </Menu.Item>
      </Menu>
    </Header>
  );
};

export default Navbar;
