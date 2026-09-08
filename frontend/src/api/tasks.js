import { authFetch } from './client.js'

const API_BASE = '/api/tasks'

export async function getTasks(limit = 50) {
  const response = await authFetch(`${API_BASE}?limit=${limit}`)
  if (!response.ok) throw new Error('获取异步任务失败')
  return response.json()
}
