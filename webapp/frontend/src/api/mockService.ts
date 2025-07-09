import axios from 'axios';

export async function fetchChartData() {
  const { data } = await axios.get('/data');
  return data;
}

export async function createTask(payload: any = {}) {
  const { data } = await axios.post('/tasks', payload);
  return data;
}

export async function listTasks() {
  const { data } = await axios.get('/tasks');
  return data;
}

export async function getTask(id: string) {
  const { data } = await axios.get(`/tasks/${id}`);
  return data;
}
