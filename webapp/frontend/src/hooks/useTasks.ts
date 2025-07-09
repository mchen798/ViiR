import create from 'zustand';
import * as api from '../api/mockService';

interface TaskInfo {
  status: string;
  result?: any;
}

interface TaskState {
  tasks: Record<string, TaskInfo>;
  fetchTasks: () => Promise<void>;
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: {},
  fetchTasks: async () => {
    const data = await api.listTasks();
    set({ tasks: data });
  },
}));
