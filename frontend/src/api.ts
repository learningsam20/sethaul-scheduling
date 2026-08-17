const API = import.meta.env.VITE_API_BASE || '/api';

export type User = {
  user_id: string;
  username: string;
  role: string;
  display_name: string;
  driver_id?: string | null;
  facility_id?: string | null;
  carrier_id?: string | null;
  customer_key?: string | null;
  theme_pref?: string;
};

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('setuhaul_token');
  return token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...authHeaders(), ...(init?.headers || {}) } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  login: (username: string, password: string) =>
    req<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => req<{ user: User }>('/auth/me'),
  seedUsers: () => req<{ users: User[]; default_password: string }>('/auth/demo-users'),
  threads: (facility_id?: string) =>
    req<{ threads: any[] }>(`/chat/threads${facility_id ? `?facility_id=${facility_id}` : ''}`),
  thread: (id: string) => req<{ thread: any; messages: any[] }>(`/chat/threads/${id}`),
  createThread: (shipment_id?: string) =>
    req<{ thread: any; messages: any[] }>(
      `/chat/threads${shipment_id ? `?shipment_id=${encodeURIComponent(shipment_id)}` : ''}`,
      { method: 'POST' },
    ),
  chat: (message: string, thread_id?: string, shipment_id?: string) =>
    req<any>('/chat/message', {
      method: 'POST',
      body: JSON.stringify({ message, thread_id, shipment_id }),
    }),
  takeover: (thread_id: string) => req<any>(`/chat/threads/${thread_id}/takeover`, { method: 'POST' }),
  opsMessage: (thread_id: string, message: string) =>
    req<any>(`/chat/threads/${thread_id}/ops-message`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  resolveThread: (thread_id: string) =>
    req<any>(`/chat/threads/${thread_id}/resolve`, {
      method: 'POST',
    }),
  facilities: () => req<{ facilities: any[] }>('/ops/facilities'),
  inbound: (facility_id?: string) =>
    req<{ rows: any[] }>(`/ops/inbound${facility_id ? `?facility_id=${facility_id}` : ''}`),
  pending: (facility_id?: string) =>
    req<{ rows: any[] }>(`/ops/pending${facility_id ? `?facility_id=${facility_id}` : ''}`),
  decide: (appointment_id: string, approve: boolean) =>
    req<any>(`/ops/pending/${appointment_id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ approve }),
    }),
  cancelAppointment: (appointment_id: string, reason?: string) =>
    req<any>(`/ops/appointments/${appointment_id}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'Cancelled by warehouse' }),
    }),
  exceptions: (facility_id?: string) =>
    req<{ rows: any[] }>(`/ops/exceptions${facility_id ? `?facility_id=${facility_id}` : ''}`),
  schedule: (facility_id: string, shipment_id?: string) =>
    req<any>(`/ops/schedule/${facility_id}${shipment_id ? `?shipment_id=${shipment_id}` : ''}`, { method: 'POST' }),
  agentHealth: (facility_id?: string) =>
    req<any>(`/analytics/health${facility_id ? `?facility_id=${facility_id}` : ''}`),
  weeklyGenerate: () => req<any>('/analytics/weekly/generate', { method: 'POST' }),
  weekly: (scope_type?: string) =>
    req<{ reports: any[] }>(`/analytics/weekly${scope_type ? `?scope_type=${scope_type}` : ''}`),
  insights: () =>
    req<{
      insights: any[];
      last_refreshed_at?: string | null;
      iso_week?: string;
      model?: string | null;
      source?: string | null;
      note?: string | null;
    }>('/analytics/insights'),
  insightsRefresh: () => req<any>('/analytics/insights/refresh', { method: 'POST' }),
  adminUsers: () => req<{ users: any[]; roles: string[] }>('/admin/users'),
  createUser: (body: any) => req<any>('/admin/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id: string, body: any) =>
    req<any>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteUser: (id: string) => req<any>(`/admin/users/${id}`, { method: 'DELETE' }),
  settings: () => req<{ settings: any[] }>('/admin/settings'),
  putSetting: (key: string, setting_value: string) =>
    req<any>(`/admin/settings/${key}`, { method: 'PUT', body: JSON.stringify({ setting_value }) }),
  master: (table: string) =>
    req<{ table: string; rows: any[]; columns: any[]; primary_key: string[] }>(`/admin/master/${table}`),
  createMaster: (table: string, values: Record<string, unknown>) =>
    req<any>(`/admin/master/${table}`, { method: 'POST', body: JSON.stringify({ values }) }),
  updateMaster: (table: string, key: Record<string, unknown>, values: Record<string, unknown>) =>
    req<any>(`/admin/master/${table}`, { method: 'PUT', body: JSON.stringify({ key, values }) }),
  deleteMaster: (table: string, values: Record<string, unknown>) =>
    req<any>(`/admin/master/${table}`, { method: 'DELETE', body: JSON.stringify({ values }) }),
  audit: () => req<{ events: any[] }>('/admin/audit'),
  baseline: () => req<any>('/admin/baseline'),
  putBaseline: (values: Record<string, unknown>) =>
    req<any>('/admin/baseline', { method: 'PUT', body: JSON.stringify(values) }),
  sendMessage: (body: any) =>
    req<any>('/messages/send', { method: 'POST', body: JSON.stringify(body) }),
  listMessages: (shipmentId: string) =>
    req<{ messages: any[] }>(`/messages/shipment/${shipmentId}`),
  replyMessage: (id: string, body: string) =>
    req<any>(`/messages/${id}/reply`, { method: 'POST', body: JSON.stringify({ body }) }),
  penaltyRequests: (facilityId?: string, status?: string) =>
    req<{ rows: any[] }>(`/penalty/requests${facilityId ? `?facility_id=${encodeURIComponent(facilityId)}` : ''}${status ? `${facilityId ? '&' : '?'}status=${encodeURIComponent(status)}` : ''}`),
  decidePenalty: (id: string, approve: boolean) =>
    req<any>(`/penalty/requests/${id}/decide`, { method: 'POST', body: JSON.stringify({ approve }) }),
  createPenaltyRequest: (body: any) =>
    req<any>('/penalty/requests', { method: 'POST', body: JSON.stringify(body) }),
  getAllocationPolicy: (facilityId: string) =>
    req<any>(`/ops/allocation-policy?facility_id=${encodeURIComponent(facilityId)}`),
  updateAllocationPolicy: (facilityId: string, values: Record<string, unknown>) =>
    req<any>(`/ops/allocation-policy?facility_id=${encodeURIComponent(facilityId)}`, { method: 'PUT', body: JSON.stringify(values) }),
  resumeLocation: (body: any) => req<any>('/location/resume', { method: 'POST', body: JSON.stringify(body) }),
};
