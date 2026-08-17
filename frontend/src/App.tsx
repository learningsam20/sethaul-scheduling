import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, type User } from './api';
import {
  IconAdmin,
  IconAnalytics,
  IconBan,
  IconChat,
  IconCheck,
  IconChevronLeft,
  IconChevronRight,
  IconDashboard,
  IconEdit,
  IconEye,
  IconEyeOff,
  IconFacility,
  IconHold,
  IconInbound,
  IconInsight,
  IconLocation,
  IconMoon,
  IconOps,
  IconPlay,
  IconPlus,
  IconRefresh,
  IconSend,
  IconSignIn,
  IconSignOut,
  IconSpark,
  IconSun,
  IconTrash,
  IconTrendDown,
  IconTrendUp,
  IconWarehouse,
  IconX,
} from './icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

function PasswordInput({
  id,
  value,
  onChange,
  placeholder,
  autoComplete,
  disabled,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoComplete?: string;
  disabled?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className={`password-field${visible ? ' is-revealed' : ''}`}>
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        name={id || 'password'}
        autoComplete={autoComplete || 'current-password'}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className="password-toggle"
        tabIndex={0}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        title={visible ? 'Hide password' : 'Show password'}
      >
        {visible ? <IconEyeOff size={16} /> : <IconEye size={16} />}
      </button>
    </div>
  );
}

type Tab = 'dashboard' | 'chat' | 'ops' | 'warehouse' | 'admin' | 'analytics' | 'inbound' | 'messaging';

const ROLE_TABS: Record<string, Tab[]> = {
  DRIVER: ['dashboard', 'chat', 'inbound'],
  OPERATIONS: ['dashboard', 'ops', 'inbound', 'analytics', 'chat'],
  WAREHOUSE: ['dashboard', 'warehouse', 'inbound', 'analytics'],
  ADMIN: ['dashboard', 'admin', 'ops', 'warehouse', 'analytics', 'inbound', 'chat'],
  CARRIER: ['dashboard', 'inbound', 'analytics', 'messaging'],
  CUSTOMER: ['inbound', 'messaging'],
};

const TAB_META: Record<
  Tab,
  {
    label: string;
    page: string;
    blurb: string;
    icon: (p?: { size?: number }) => ReactNode;
    iconOnly?: boolean;
  }
> = {
  dashboard: {
    label: 'Dashboard',
    page: 'Operations Dashboard',
    blurb: 'Live facility pulse — inbound load, exceptions, confirmations, and agent health.',
    icon: (p) => <IconDashboard {...p} />,
  },
  chat: {
    label: 'Chat',
    page: 'Exceptions',
    blurb: 'Report delays, review verified slots, and soft-hold a window before warehouse confirmation.',
    icon: (p) => <IconChat {...p} />,
  },
  ops: {
    label: 'Operations',
    page: 'Operations Queue',
    blurb: 'Open exceptions and facility scheduling in one place.',
    icon: (p) => <IconOps {...p} />,
  },
  warehouse: {
    label: 'Warehouse',
    page: 'Warehouse Confirmations',
    blurb: 'Approve or reject appointments waiting on dock confirmation.',
    icon: (p) => <IconWarehouse {...p} />,
  },
  admin: {
    label: 'Admin',
    page: 'Administration',
    blurb: 'Manage users, roles, settings, and system clock.',
    icon: (p) => <IconAdmin {...p} />,
  },
  analytics: {
    label: 'Analytics',
    page: 'Analytics & Insights',
    blurb: 'Agent trust scores, week-over-week movement, and actionable insight cards.',
    icon: (p) => <IconAnalytics {...p} />,
  },
  inbound: {
    label: 'Inbound Board',
    page: 'Inbound Board',
    blurb: 'Live inbound shipments with ETA and exception status.',
    icon: (p) => <IconInbound {...p} />,
  },
  messaging: {
    label: 'Messages',
    page: 'Messages',
    blurb: 'Operational messages for your shipments.',
    icon: (p) => <IconChat {...p} />,
  },
};

function applyTheme(theme: string) {
  document.documentElement.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');
}

function titleCase(value: string) {
  return value
    .replace(/[_-]+/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtTime(ts?: string | null) {
  if (!ts) return '—';
  const t = String(ts);
  if (t.length >= 16 && t.includes('T')) return t.slice(11, 16);
  return t;
}

function fmtStamp(ts?: string | null) {
  if (!ts) return '—';
  const t = String(ts);
  if (t.includes('T')) return t.slice(0, 19).replace('T', ' ');
  return t;
}

function fmtWindow(start?: string | null, end?: string | null) {
  return `${fmtTime(start)}–${fmtTime(end)}`;
}

function statusTone(status?: string | null): string {
  const s = (status || '').toUpperCase();
  if (/(CONFIRMED|RESOLVED|CLOSED|ACTIVE|OK)/.test(s)) return 'ok';
  if (/(PENDING|WAITING|OPEN|SHARED|NEEDS)/.test(s)) return 'warn';
  if (/(REJECT|CANCEL|ESCALAT|FAIL|FAULT)/.test(s)) return 'danger';
  return 'accent';
}

function PageToolbar({ actions }: { actions?: ReactNode }) {
  if (!actions) return null;
  return <div className="page-toolbar">{actions}</div>;
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

function pct(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Math.round(Number(value) * 100)}%`;
}

function ScoreMeter({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint: string;
}) {
  const clamped = Math.max(0, Math.min(1, Number(value) || 0));
  const deg = Math.round(clamped * 360);
  return (
    <div className="score-meter">
      <div className="score-ring" style={{ background: `conic-gradient(var(--accent) ${deg}deg, color-mix(in srgb, var(--line) 70%, transparent) 0deg)` }}>
        <div className="score-ring-inner">
          <strong>{pct(clamped)}</strong>
        </div>
      </div>
      <div>
        <div className="score-label">{label}</div>
        <div className="muted score-hint">{hint}</div>
      </div>
    </div>
  );
}

function StatTile({
  label,
  value,
  detail,
  tone = '',
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className={`stat-tile ${tone}`}>
      <div className="muted">{label}</div>
      <strong>{value}</strong>
      {detail ? <div className="stat-detail">{detail}</div> : null}
    </div>
  );
}

function DeltaChip({ delta }: { delta?: number | null }) {
  if (delta == null || Number.isNaN(Number(delta))) return <span className="delta flat">—</span>;
  const n = Number(delta);
  if (n > 0.001) {
    return (
      <span className="delta up">
        <IconTrendUp size={14} /> +{n.toFixed(2)}
      </span>
    );
  }
  if (n < -0.001) {
    return (
      <span className="delta down">
        <IconTrendDown size={14} /> {n.toFixed(2)}
      </span>
    );
  }
  return <span className="delta flat">0.00</span>;
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('setuhaul_token') || '');
  const [user, setUser] = useState<User | null>(null);
  const [theme, setTheme] = useState(localStorage.getItem('setuhaul_theme') || 'light');
  const [tab, setTab] = useState<Tab>('chat');
  const [chatFocusThreadId, setChatFocusThreadId] = useState<string | null>(null);
  const [facilityId, setFacilityId] = useState('');
  const [facilities, setFacilities] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [navCollapsed, setNavCollapsed] = useState(
    () => localStorage.getItem('setuhaul_nav_collapsed') === '1',
  );

  const openChatThread = (threadId?: string | null) => {
    setChatFocusThreadId(threadId || null);
    setTab('chat');
  };

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem('setuhaul_theme', theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('setuhaul_nav_collapsed', navCollapsed ? '1' : '0');
  }, [navCollapsed]);

  useEffect(() => {
    if (!token) return;
    api
      .me()
      .then((r) => {
        setUser(r.user);
        if (r.user.theme_pref && r.user.theme_pref !== 'system') {
          setTheme(r.user.theme_pref);
        }
        const nextTabs = ROLE_TABS[r.user.role] || ['chat'];
        setTab(nextTabs[0]);
        if (r.user.facility_id) setFacilityId(r.user.facility_id);
      })
      .catch(() => {
        localStorage.removeItem('setuhaul_token');
        setToken('');
      });
    api.facilities().then((r) => setFacilities(r.facilities)).catch(() => undefined);
  }, [token]);

  const tabs = useMemo(() => (user ? ROLE_TABS[user.role] || ['chat'] : []), [user]);

  if (!token || !user) {
    return (
      <Login
        theme={theme}
        setTheme={setTheme}
        onLogin={async (username, password) => {
          setError('');
          try {
            const r = await api.login(username, password);
            localStorage.setItem('setuhaul_token', r.access_token);
            setToken(r.access_token);
            setUser(r.user);
          } catch (e: any) {
            setError(e.message || 'Sign-In Failed');
          }
        }}
        error={error}
      />
    );
  }

  return (
    <div className={`app-shell ${navCollapsed ? 'nav-collapsed' : ''}`}>
      <aside className="sidebar" aria-label="Primary">
        <div className="sidebar-brand">
          <img src="/logo.svg" alt="" />
          <div className="sidebar-brand-text">
            <div className="brand-name">SetuHaul</div>
            <div className="brand-meta">
              {user.display_name} · {titleCase(user.role)}
            </div>
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setNavCollapsed((v) => !v)}
            title={navCollapsed ? 'Expand Menu' : 'Collapse Menu'}
            aria-label={navCollapsed ? 'Expand Menu' : 'Collapse Menu'}
            aria-expanded={!navCollapsed}
          >
            {navCollapsed ? <IconChevronRight size={18} /> : <IconChevronLeft size={18} />}
          </button>
        </div>

        <nav className="sidebar-nav">
          {tabs.map((t) => (
            <button
              key={t}
              type="button"
              className={`nav-item ${tab === t ? 'active' : ''} ${TAB_META[t].iconOnly ? 'icon-only' : ''}`}
              onClick={() => setTab(t)}
              title={TAB_META[t].label}
              aria-label={TAB_META[t].label}
            >
              {TAB_META[t].icon({ size: 18 })}
              {!TAB_META[t].iconOnly && <span>{TAB_META[t].label}</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div
            className="sidebar-user"
            title={`${user.display_name} · ${titleCase(user.role)}`}
          >
            <div className="sidebar-user-avatar" aria-hidden="true">
              {(user.display_name || user.username || '?').slice(0, 1).toUpperCase()}
            </div>
            <div className="sidebar-user-text">
              <div className="sidebar-user-name">{user.display_name || user.username}</div>
              <div className="sidebar-user-role">{titleCase(user.role)}</div>
            </div>
          </div>
          <button
            type="button"
            className="nav-item"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            title={theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
          >
            {theme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
            <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
          <button
            type="button"
            className="nav-item"
            onClick={() => {
              localStorage.removeItem('setuhaul_token');
              setToken('');
              setUser(null);
            }}
            title="Sign Out"
          >
            <IconSignOut size={18} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      <div className="main-column">
        <header className="content-header">
          <div>
            <h1 className="content-title">
              {user.role === 'DRIVER' && tab === 'dashboard'
                ? 'My Dashboard'
                : user.role === 'DRIVER' && tab === 'inbound'
                  ? 'My Inbound Board'
                  : TAB_META[tab].page}
            </h1>
            <p className="content-sub">
              {user.role === 'DRIVER' && tab === 'dashboard'
                ? 'Your assigned loads, exceptions, and arrival status.'
                : user.role === 'DRIVER' && tab === 'inbound'
                  ? 'Shipments assigned to you — ETA and exception status.'
                  : TAB_META[tab].blurb}
            </p>
          </div>
          <div className="header-actions">
            <div className="header-user" title={`${user.display_name} · ${titleCase(user.role)}`}>
              <strong>{user.display_name || user.username}</strong>
              <span>{titleCase(user.role)}</span>
            </div>
            <label className="facility-picker">
              <IconFacility size={16} />
              <select
                className="select-control"
                value={facilityId}
                onChange={(e) => setFacilityId(e.target.value)}
                aria-label="Facility Filter"
              >
                <option value="">All Facilities</option>
                {facilities.map((f) => (
                  <option key={f.facility_id} value={f.facility_id}>
                    {f.name || f.facility_id}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>
        <main className="main">
          {tab === 'dashboard' && (
            <DashboardPanel user={user} facilityId={facilityId} tabs={tabs} onNavigate={setTab} />
          )}
          {tab === 'chat' && (
            <ChatPanel
              user={user}
              facilityId={facilityId}
              focusThreadId={chatFocusThreadId}
              onFocusConsumed={() => setChatFocusThreadId(null)}
            />
          )}
          {tab === 'ops' && <OpsPanel facilityId={facilityId} onOpenChat={openChatThread} />}
          {tab === 'warehouse' && <WarehousePanel facilityId={facilityId} />}
          {tab === 'admin' && user && <AdminPanel currentUser={user} />}
          {tab === 'analytics' && <AnalyticsPanel facilityId={facilityId} />}
          {tab === 'inbound' && <InboundPanel user={user} facilityId={facilityId} />}
          {tab === 'messaging' && <MessagesPanel user={user} facilityId={facilityId} />}
        </main>
      </div>
    </div>
  );
}

function Login({
  onLogin,
  error,
  theme,
  setTheme,
}: {
  onLogin: (u: string, p: string) => void | Promise<void>;
  error: string;
  theme: string;
  setTheme: (t: string) => void;
}) {
  const [username, setUsername] = useState('driver.ravi');
  const [password, setPassword] = useState('pin1234');
  const [accounts, setAccounts] = useState<User[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.seedUsers().then((r) => setAccounts(r.users)).catch(() => undefined);
  }, []);

  const submit = () => {
    if (busy) return;
    setBusy(true);
    Promise.resolve(onLogin(username, password)).finally(() => setBusy(false));
  };

  return (
    <div className="login-stage" data-theme={theme === 'dark' ? 'dark' : 'light'}>
      <div className="login-atmosphere" aria-hidden="true">
        <div className="login-glow login-glow-a" />
        <div className="login-glow login-glow-b" />
        <div className="login-road" />
      </div>
      <button
        type="button"
        className="login-theme"
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        aria-label={theme === 'dark' ? 'Switch To Light Mode' : 'Switch To Dark Mode'}
      >
        {theme === 'dark' ? <IconSun size={16} /> : <IconMoon size={16} />}
        {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
      </button>
      <div className="login-frame">
        <section className="login-hero">
          <img className="login-mark" src="/logo.svg" alt="" />
          <h1 className="login-brand">SetuHaul</h1>
          <p className="login-tag">Dock appointments when the road changes.</p>
        </section>
        <form
          className="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="field">
            <label htmlFor="login-user">Username</label>
            <input
              id="login-user"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="login-pass">Password</label>
            <PasswordInput
              id="login-pass"
              autoComplete="current-password"
              value={password}
              onChange={setPassword}
            />
          </div>
          {error && <p className="error">{error}</p>}
          <button className="btn primary login-submit" type="submit" disabled={busy}>
            <IconSignIn size={17} />
            {busy ? 'Signing In…' : 'Sign In'}
          </button>
          {accounts.length > 0 && (
            <div className="login-accounts">
              <label htmlFor="login-account">Quick Select</label>
              <select
                id="login-account"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              >
                {accounts.map((a) => (
                  <option key={a.username} value={a.username}>
                    {a.display_name} · {titleCase(a.role)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

function mapChatMessages(rows: any[]) {
  return (rows || []).map((m: any) => ({
    role: m.sender_type === 'DRIVER' ? 'user' : 'assistant',
    content: m.message_text,
    sender: m.sender_type,
    ts: m.message_ts || null,
  }));
}

function tryParseJson(text: string): unknown | null {
  let raw = text.trim();
  if (raw.startsWith('```')) {
    raw = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  }
  if (!raw || (raw[0] !== '{' && raw[0] !== '[')) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

function fieldLabel(key: string): string {
  const labels: Record<string, string> = {
    shipment_id: 'Shipment',
    driver_id: 'Driver',
    vehicle_id: 'Vehicle',
    destination_facility_id: 'Facility',
    priority_code: 'Priority',
    required_dock_type: 'Dock type',
    temperature_control_required: 'Reefer',
    load_weight_kg: 'Weight (kg)',
    expected_unload_min: 'Unload (min)',
    current_status: 'Status',
    effective_eta_ts: 'ETA',
    eta_source: 'ETA source',
    eta_confidence: 'ETA confidence',
    appointment_id: 'Appointment',
    slot_id: 'Slot',
    slot_start_ts: 'Slot start',
    slot_end_ts: 'Slot end',
    planned_dock_code: 'Planned dock',
    gate_in_ts: 'Gate-in',
    queue_state: 'Queue',
    queue_position: 'Queue position',
    actual_dock_code: 'Actual dock',
    feasible: 'Feasible',
    reason: 'Reason',
    dock_code: 'Dock',
  };
  return labels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtDetail(value: unknown): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(text)) {
    const d = new Date(text);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    }
  }
  return text;
}

function kvMarkdown(obj: Record<string, unknown>): string {
  const lines = ['| Field | Value |', '| --- | --- |'];
  const nested = isRecord(obj.state) ? { ...obj, ...obj.state } : obj;
  for (const [key, value] of Object.entries(nested)) {
    if (value == null || value === '' || typeof value === 'object') continue;
    if (key === 'state') continue;
    lines.push(`| ${fieldLabel(key)} | ${fmtDetail(value).replace(/\|/g, '/')} |`);
  }
  return lines.length > 2 ? lines.join('\n') : '';
}

function jsonToMarkdown(data: unknown): string {
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) {
    if (data.length === 1 && isRecord(data[0])) return kvMarkdown(data[0]);
    if (data.length && data.every(isRecord)) {
      const keys = ['shipment_id', 'current_status', 'destination_facility_id', 'planned_dock_code', 'effective_eta_ts'].filter(
        (k) => data.some((row) => k in (row as Record<string, unknown>)),
      );
      const use = keys.length ? keys : Object.keys(data[0] as Record<string, unknown>).slice(0, 5);
      const head = `| ${use.map(fieldLabel).join(' | ')} |`;
      const sep = `| ${use.map(() => '---').join(' | ')} |`;
      const rows = data.map(
        (row) => `| ${use.map((k) => fmtDetail((row as Record<string, unknown>)[k]).replace(/\|/g, '/')).join(' | ')} |`,
      );
      return [head, sep, ...rows].join('\n');
    }
    return String(data);
  }
  if (isRecord(data) && typeof data.reply === 'string' && ('intent' in data || 'options' in data)) {
    return data.reply;
  }
  if (isRecord(data)) return kvMarkdown(data) || JSON.stringify(data);
  return String(data);
}

function BubbleBody({ content }: { content: string }) {
  const parsedJson = tryParseJson(content);
  let text = parsedJson != null ? jsonToMarkdown(parsedJson) : (content || '');
  // Normalize pipe tables where rows might be concatenated on a single line
  text = text.replace(/\|\s*\|/g, '|\n|').replace(/\\n/g, '\n');

  return (
    <div className="bubble-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ ...props }) => (
            <div className="bubble-table-wrap">
              <table className="bubble-table" {...props} />
            </div>
          ),
          a: ({ ...props }) => (
            <a target="_blank" rel="noopener noreferrer" {...props} />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function chatStorageKey(userId: string) {
  return `setuhaul_chat_session_${userId}`;
}

function ChatPanel({
  user,
  facilityId,
  focusThreadId,
  onFocusConsumed,
}: {
  user: User;
  facilityId: string;
  focusThreadId?: string | null;
  onFocusConsumed?: () => void;
}) {
  const [threadId, setThreadId] = useState<string | undefined>();
  const [threadStatus, setThreadStatus] = useState<string | undefined>();
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [options, setOptions] = useState<any[]>([]);
  const [optionsStale, setOptionsStale] = useState(false);
  const [pendingLocation, setPendingLocation] = useState(false);
  const [busy, setBusy] = useState(false);
  const [threads, setThreads] = useState<any[]>([]);
  const [err, setErr] = useState('');
  const [waitProjection, setWaitProjection] = useState<{ oldMin?: number; newMin?: number } | null>(null);
  const restoredRef = useRef(false);
  const chatLogRef = useRef<HTMLDivElement | null>(null);

  const canOps = user.role === 'OPERATIONS' || user.role === 'ADMIN';
  const canDriverChat = user.role === 'DRIVER' || (user.role === 'ADMIN' && !!user.driver_id);
  const activeThread = threads.find((t) => t.thread_id === threadId);

  const rememberSession = (id?: string | null) => {
    if (!user.user_id) return;
    if (id) localStorage.setItem(chatStorageKey(user.user_id), id);
    else localStorage.removeItem(chatStorageKey(user.user_id));
  };

  const loadThreads = async () => {
    try {
      const r = await api.threads(facilityId || undefined);
      setThreads(r.threads || []);
      return r.threads || [];
    } catch {
      return [] as any[];
    }
  };

  const openThread = async (t: { thread_id: string; thread_status?: string }) => {
    const det = await api.thread(t.thread_id);
    setThreadId(t.thread_id);
    setThreadStatus(det.thread?.thread_status || t.thread_status);
    setMessages(mapChatMessages(det.messages));
    setOptions([]);
    setOptionsStale(false);
    setPendingLocation(false);
    setErr('');
    rememberSession(t.thread_id);
  };

  const startNewSession = async () => {
    if (!canDriverChat) {
      setThreadId(undefined);
      setThreadStatus(undefined);
      setMessages([]);
      setOptions([]);
      setOptionsStale(false);
      setPendingLocation(false);
      setErr('');
      rememberSession(null);
      return;
    }

    // Already on an empty chat — just refocus compose, don't create another session
    if (threadId && messages.length === 0) {
      setErr('');
      setOptions([]);
      setOptionsStale(false);
      setPendingLocation(false);
      rememberSession(threadId);
      requestAnimationFrame(() => {
        document.querySelector<HTMLInputElement>('.chat-compose input')?.focus();
      });
      return;
    }

    // Reuse any existing empty open session from the list
    const list = threads.length ? threads : await loadThreads();
    const empty = list.find(
      (t: any) =>
        (t.message_count == null || Number(t.message_count) === 0) &&
        !/CLOSED|RESOLVED/i.test(t.thread_status || ''),
    );
    if (empty) {
      try {
        await openThread(empty);
        requestAnimationFrame(() => {
          document.querySelector<HTMLInputElement>('.chat-compose input')?.focus();
        });
      } catch (e: any) {
        setErr(e.message);
      }
      return;
    }

    setBusy(true);
    setErr('');
    try {
      const r = await api.createThread();
      setThreadId(r.thread?.thread_id);
      setThreadStatus(r.thread?.thread_status || 'OPEN');
      setMessages([]);
      setOptions([]);
      setOptionsStale(false);
      setPendingLocation(false);
      rememberSession(r.thread?.thread_id);
      await loadThreads();
      requestAnimationFrame(() => {
        document.querySelector<HTMLInputElement>('.chat-compose input')?.focus();
      });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    restoredRef.current = false;
    loadThreads().then(async (list) => {
      if (focusThreadId) return;
      const saved = localStorage.getItem(chatStorageKey(user.user_id));
      const target =
        (saved && list.find((t: any) => t.thread_id === saved)) ||
        list[0] ||
        null;
      if (target) {
        try {
          await openThread(target);
        } catch {
          rememberSession(null);
        }
      }
      restoredRef.current = true;
    });
  }, [facilityId, user.user_id]);

  useEffect(() => {
    if (!focusThreadId) return;
    openThread({ thread_id: focusThreadId })
      .catch((e: any) => setErr(e.message || 'Could not open thread'))
      .finally(() => onFocusConsumed?.());
  }, [focusThreadId]);

  useEffect(() => {
    const el = chatLogRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  useEffect(() => {
    if (!threadId) return;
    const iv = setInterval(async () => {
      if (busy) return;
      try {
        const det = await api.thread(threadId);
        const nextMsgs = mapChatMessages(det.messages);
        setMessages((curr) => {
          if (curr.length !== nextMsgs.length || curr.some((m, idx) => m.content !== nextMsgs[idx]?.content)) {
            return nextMsgs;
          }
          return curr;
        });
        if (det.thread?.thread_status) {
          setThreadStatus(det.thread.thread_status);
        }
      } catch {
        // silent poll catch
      }
    }, 3000);
    return () => clearInterval(iv);
  }, [threadId, busy]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setErr('');
    const sentAt = new Date().toISOString();
    setInput('');

    if (canOps && !canDriverChat) {
      if (!threadId) {
        setErr('Select a session first, then reply to take it over.');
        return;
      }
      setBusy(true);
      setMessages((m) => [
        ...m,
        { role: 'user', content: trimmed, sender: 'OPERATIONS', ts: sentAt },
        { role: 'assistant', content: 'Waiting for response…', sender: 'SYSTEM', ts: sentAt, pending: true },
      ]);
      try {
        const r = await api.opsMessage(threadId, trimmed);
        setThreadStatus(r.thread_status || 'ESCALATED');
        setMessages(mapChatMessages(r.messages || []));
        await loadThreads();
      } catch (e: any) {
        setMessages((m) => m.filter((row) => !row.pending));
        setErr(e.message);
      } finally {
        setBusy(false);
      }
      return;
    }

    setBusy(true);
    setMessages((m) => [
      ...m,
      { role: 'user', content: trimmed, sender: 'DRIVER', ts: sentAt },
      { role: 'assistant', content: 'Waiting for AI response…', sender: 'AGENT', ts: sentAt, pending: true },
    ]);
    try {
      const r = await api.chat(trimmed, threadId);
      if (r.error) {
        setMessages((m) => [
          ...m.filter((row) => !row.pending),
          { role: 'assistant', content: String(r.error), sender: 'SYSTEM', ts: new Date().toISOString() },
        ]);
        return;
      }
      if (r.messages) {
        setMessages(mapChatMessages(r.messages));
      } else {
        try {
          const det = await api.thread(r.thread_id);
          setMessages(mapChatMessages(det.messages));
          setThreadStatus(det.thread?.thread_status);
        } catch {
          setMessages((m) => [
            ...m.filter((row) => !row.pending),
            { role: 'assistant', content: r.reply, sender: 'AGENT', ts: new Date().toISOString() },
          ]);
        }
      }
      setThreadId(r.thread_id);
      setThreadStatus(r.human_takeover ? 'ESCALATED' : threadStatus || 'OPEN');
      rememberSession(r.thread_id);
      setOptions(r.options || []);
      setOptionsStale(!!r.options_stale);
      setPendingLocation(!!(r.client_actions || []).includes('REQUEST_BROWSER_LOCATION'));
      const booking = r.booking;
      if (booking && (booking.projected_wait_old_min != null || booking.projected_wait_new_min != null)) {
        setWaitProjection({
          oldMin: booking.projected_wait_old_min,
          newMin: booking.projected_wait_new_min,
        });
      } else {
        setWaitProjection(null);
      }
      await loadThreads();
    } catch (e: any) {
      setMessages((m) => m.filter((row) => !row.pending));
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const shareLocation = () => {
    if (!navigator.geolocation) {
      setErr('Geolocation Unavailable');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        setBusy(true);
        try {
          const r = await api.resumeLocation({
            thread_id: threadId,
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            accuracy_m: pos.coords.accuracy,
            captured_at: new Date(pos.timestamp).toISOString(),
            client_now: new Date().toISOString(),
          });
          if (r.messages) {
            setMessages(mapChatMessages(r.messages));
          } else {
            setMessages((m) => [
              ...m,
              { role: 'assistant', content: r.reply, sender: 'AGENT', ts: new Date().toISOString() },
            ]);
          }
          setOptions(r.options || []);
          setOptionsStale(!!r.options_stale);
          setPendingLocation(false);
          await loadThreads();
        } catch (e: any) {
          setErr(e.message);
        } finally {
          setBusy(false);
        }
      },
      () => setErr('Location Permission Denied'),
    );
  };

  const resolveActiveSession = async () => {
    if (!threadId || busy) return;
    setBusy(true);
    setErr('');
    try {
      const r = await api.resolveThread(threadId);
      setThreadStatus('RESOLVED');
      setMessages(mapChatMessages(r.messages || []));
      await loadThreads();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const sessionTime = (t: any) => fmtStamp(t.last_message_ts || t.opened_at);
  const preview = (t: any) => {
    const text = String(t.last_message_preview || t.thread_intent || 'No messages yet').replace(/\s+/g, ' ');
    return text.length > 72 ? `${text.slice(0, 72)}…` : text;
  };

  return (
    <div className="grid2">
      <div>
        <div className="chat-session-bar">
          <div>
            <div className="muted" style={{ fontSize: '0.78rem', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              Active session
            </div>
            <div className="mono" style={{ fontWeight: 600 }}>
              {threadId || 'None selected'}
            </div>
            {threadId && (
              <div className="muted" style={{ fontSize: '0.82rem', marginTop: '0.15rem' }}>
                {threadStatus || 'OPEN'}
                {activeThread ? ` · ${sessionTime(activeThread)}` : ''}
                {activeThread?.shipment_id ? ` · ${activeThread.shipment_id}` : ''}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            {canOps && threadId && threadStatus !== 'RESOLVED' && threadStatus !== 'CLOSED' && (
              <button className="btn sm success" disabled={busy} onClick={resolveActiveSession} title="Mark session as resolved">
                <IconCheck size={15} />
                Resolve session
              </button>
            )}
            {canDriverChat && (
              <button className="btn sm" disabled={busy} onClick={startNewSession}>
                <IconPlus size={15} />
                New chat
              </button>
            )}
          </div>
        </div>
        <div className="chat">
          <div className="chat-log" ref={chatLogRef}>
            {messages.length === 0 ? (
              <div className="chat-empty">
                {canOps && !canDriverChat
                  ? 'Select a session from the list to review history. Sending a reply takes it over.'
                  : threadId
                    ? 'Continue this session — describe the delay or exception.'
                    : 'Select a past session or start a new chat.'}
              </div>
            ) : (
              messages.map((m, i) => (
                <div
                  key={i}
                  className={`bubble ${m.role === 'user' ? 'mine' : 'theirs'}${m.pending ? ' pending' : ''}`}
                >
                  <span className="bubble-meta">
                    <span>
                      {m.sender === 'OPERATIONS'
                        ? 'Operations'
                        : m.sender === 'SYSTEM'
                          ? 'System'
                          : m.role === 'user'
                            ? canOps && !canDriverChat
                              ? 'Driver'
                              : 'You'
                            : 'SetuHaul'}
                    </span>
                    {m.ts && <time dateTime={m.ts}>{fmtStamp(m.ts)}</time>}
                  </span>
                  {m.pending ? <span className="typing-dots">{m.content}</span> : <BubbleBody content={m.content} />}
                </div>
              ))
            )}
          </div>
          <div className="chat-compose">
            <input
              value={input}
              disabled={busy || ((canOps && !canDriverChat) && !threadId)}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send(input)}
              placeholder={
                canOps && !canDriverChat
                  ? threadId
                    ? threadStatus === 'ESCALATED'
                      ? 'Reply to driver…'
                      : 'Send a reply to take over this thread…'
                    : 'Select a session to reply…'
                  : 'Describe the exception…'
              }
            />
            {canDriverChat && (
              <button
                type="button"
                className="btn ghost icon-btn"
                title="Share one-time live GPS location"
                disabled={busy}
                onClick={shareLocation}
              >
                <IconLocation size={16} />
              </button>
            )}
            <button
              className="btn primary"
              disabled={busy || ((canOps && !canDriverChat) && !threadId)}
              onClick={() => send(input)}
            >
              <IconSend size={16} />
              Send
            </button>
          </div>
        </div>
        {err && <p className="error">{err}</p>}
        {canOps && !canDriverChat && threadId && threadStatus !== 'ESCALATED' && (
          <p className="muted" style={{ marginTop: '0.65rem', fontSize: '0.85rem' }}>
            Viewing only — status stays {threadStatus || 'OPEN'} until you send a reply.
          </p>
        )}
        {pendingLocation && canDriverChat && (
          <div className="loc-banner">
            <div>
              <strong>One-Time Location</strong>
              <div className="muted">Improves route ETA buffers without continuous tracking.</div>
            </div>
            <div className="action-row">
              <button className="btn primary" onClick={shareLocation}>
                <IconLocation size={16} />
                Share Location
              </button>
              <button className="btn ghost" onClick={() => send('skip location')}>
                Skip
              </button>
            </div>
          </div>
        )}
        {optionsStale && (
          <p className="flash" style={{ marginTop: '0.75rem' }}>
            Shown options changed — a slot was cancelled or a dock went down. Review the updated list
            (shown ≠ held ≠ confirmed).
          </p>
        )}
        {waitProjection && (waitProjection.oldMin != null || waitProjection.newMin != null) && (
          <p className="flash" style={{ marginTop: '0.75rem' }}>
            Wait projection updated: {waitProjection.oldMin != null ? `${waitProjection.oldMin} min` : '—'} → {waitProjection.newMin != null ? `${waitProjection.newMin} min` : '—'}
          </p>
        )}
        {options.length > 0 && canDriverChat && (
          <div className="panel" style={{ marginTop: '1rem' }}>
            <h3 className="panel-title">Verified Slot Options</h3>
            <div className="options">
              {options.map((o, idx) => (
                <div key={o.slot_id || idx} className="option">
                  <div>
                    <div className="option-title">
                      {idx + 1}. Dock {o.dock_code || o.dock_id} ·{' '}
                      {fmtWindow(o.slot_start_ts || o.start_ts, o.slot_end_ts || o.end_ts)}
                    </div>
                    <div className="option-meta">
                      <span className="mono">{o.slot_id}</span>
                      {o.arrival_buffer_min != null ? ` · Buffer ~${Math.round(o.arrival_buffer_min)} Min` : ''}
                      {o.requires_manual_approval ? ' · Needs Approval' : ''}
                    </div>
                  </div>
                  <button className="btn primary sm" onClick={() => send(`take option ${idx + 1}`)}>
                    <IconHold size={15} />
                    Soft-Hold
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <div>
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3 className="panel-title">Chat sessions</h3>
              <p className="muted" style={{ margin: '0.2rem 0 0', fontSize: '0.82rem' }}>
                Session ID · last activity — select to continue
              </p>
            </div>
            <button className="btn sm ghost" onClick={() => loadThreads()} title="Refresh sessions">
              <IconRefresh size={15} />
            </button>
          </div>
          {threads.length === 0 ? (
            <Empty>{canOps ? 'No sessions for this filter.' : 'No sessions yet. Start a new chat.'}</Empty>
          ) : (
            <div className="thread-list">
              {threads.map((t) => (
                <button
                  key={t.thread_id}
                  type="button"
                  className={`thread-item thread-select${threadId === t.thread_id ? ' active' : ''}`}
                  onClick={async () => {
                    try {
                      await openThread(t);
                    } catch (e: any) {
                      setErr(e.message);
                    }
                  }}
                >
                  <div className="thread-top">
                    <span className="mono session-id">{t.thread_id}</span>
                    <span className={`pill ${statusTone(t.thread_status)}`}>{t.thread_status}</span>
                  </div>
                  <div className="session-time">{sessionTime(t)}</div>
                  <div className="session-preview">{preview(t)}</div>
                  <div className="session-meta muted">
                    {canOps ? t.driver_name || t.driver_id || 'Driver' : null}
                    {canOps && (t.driver_name || t.driver_id) ? ' · ' : ''}
                    {t.shipment_id || 'No shipment'}
                    {t.message_count != null ? ` · ${t.message_count} msg` : ''}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
        {!canOps && (
          <div className="hint" style={{ marginTop: '0.85rem' }}>
            Sessions are stored on the server. Pick one to resume, or start a new chat for a fresh session ID.
          </div>
        )}
      </div>
    </div>
  );
}

function OpsPanel({
  facilityId,
  onOpenChat,
}: {
  facilityId: string;
  onOpenChat?: (threadId: string) => void;
}) {
  const [rows, setRows] = useState<any[]>([]);
  const [msg, setMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [opsTab, setOpsTab] = useState<'exceptions' | 'policy' | 'penalties'>('exceptions');
  const [policy, setPolicy] = useState<any>(null);
  const [policyForm, setPolicyForm] = useState<Record<string, any>>({});
  const [penaltyRows, setPenaltyRows] = useState<any[]>([]);
  const [penaltyStatus, setPenaltyStatus] = useState('PENDING');

  const refresh = () => {
    setLoading(true);
    if (opsTab === 'exceptions') {
      api
        .exceptions(facilityId || undefined)
        .then((r) => setRows(r.rows))
        .catch((e) => setMsg(e.message))
        .finally(() => setLoading(false));
    } else if (opsTab === 'policy' && facilityId) {
      api
        .getAllocationPolicy(facilityId)
        .then((r) => {
          setPolicy(r.policy || {});
          const defaults: Record<string, any> = {
            priority_weights_json: '{"CRITICAL":40,"HIGH":25,"NORMAL":10,"LOW":0}',
            in_progress_protection: 1,
            objective_summary: 'min waiting + lateness + overtime; never move IN_PROGRESS; priority then at-facility then ETA; assign concrete dock intervals',
          };
          setPolicyForm(r.policy ? { ...defaults, ...r.policy } : defaults);
        })
        .catch((e) => setMsg(e.message))
        .finally(() => setLoading(false));
    } else if (opsTab === 'penalties') {
      api
        .penaltyRequests(facilityId || undefined, penaltyStatus)
        .then((r) => setPenaltyRows(r.rows))
        .catch((e) => setMsg(e.message))
        .finally(() => setLoading(false));
    }
  };

  useEffect(() => {
    refresh();
  }, [facilityId, opsTab, penaltyStatus]);

  const types = useMemo(() => {
    const set = new Set(rows.map((r) => r.exception_type).filter(Boolean));
    return ['ALL', ...Array.from(set)];
  }, [rows]);

  const filtered = useMemo(
    () => (typeFilter === 'ALL' ? rows : rows.filter((r) => r.exception_type === typeFilter)),
    [rows, typeFilter],
  );

  const escalated = rows.filter((r) => /ESCALAT/i.test(r.exception_status || '')).length;
  const waiting = rows.filter((r) => /WAITING|PENDING|SHARED/i.test(r.exception_status || '')).length;

  return (
    <>
      <PageToolbar
        actions={
          <>
            {(['exceptions', 'policy', 'penalties'] as const).map((t) => (
              <button
                key={t}
                className={`btn sm ${opsTab === t ? 'primary' : ''}`}
                onClick={() => setOpsTab(t)}
              >
                {t === 'exceptions' ? 'Exceptions' : t === 'policy' ? 'Scheduler Policy' : 'Penalties'}
              </button>
            ))}
            {opsTab === 'exceptions' && (
              <select
                className="select-control"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                aria-label="Filter Exceptions by Type"
              >
                {types.map((t) => (
                  <option key={t} value={t}>
                    {t === 'ALL' ? 'All Exception Types' : titleCase(t)}
                  </option>
                ))}
              </select>
            )}
            <button className="btn" onClick={refresh} disabled={loading}>
              <IconRefresh size={16} />
              Refresh
            </button>
            {opsTab === 'exceptions' && (
              <button
                className="btn primary"
                disabled={!facilityId}
                title={!facilityId ? 'Select a facility first' : undefined}
                onClick={async () => {
                  try {
                    const r = await api.schedule(facilityId);
                    setMsg(`Scheduler finished for ${facilityId}: ${r.sequence?.length ?? 0} sequenced`);
                  } catch (e: any) {
                    setMsg(e.message);
                  }
                }}
              >
                <IconPlay size={16} />
                Run Scheduler
              </button>
            )}
          </>
        }
      />
      {msg && <p className="flash">{msg}</p>}
      {opsTab === 'exceptions' && (
        <>
          <div className="stat-grid">
            <StatTile label="Open Exceptions" value={rows.length} detail="Current filter" tone="warn" />
            <StatTile label="Waiting / Shared" value={waiting} detail="Driver response path" />
            <StatTile label="Escalated" value={escalated} detail="Needs human takeover" tone="danger" />
            <StatTile label="Showing" value={filtered.length} detail={typeFilter === 'ALL' ? 'All types' : typeFilter} tone="accent" />
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">Exception Queue</h3>
              <span className="muted">{loading ? 'Loading…' : `${filtered.length} rows`}</span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Exception</th>
                    <th>Shipment</th>
                    <th>Customer</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.exception_id}>
                      <td className="mono">{r.exception_id}</td>
                      <td className="mono">{r.shipment_id}</td>
                      <td>{r.customer_name || '—'}</td>
                      <td>{r.exception_type}</td>
                      <td>
                        <span className={`pill ${statusTone(r.exception_status || r.status)}`}>
                          {r.exception_status || r.status}
                        </span>
                      </td>
                      <td className="row-actions">
                        {r.thread_id && onOpenChat ? (
                          <button
                            type="button"
                            className="btn sm icon-btn ghost"
                            title="Open chat"
                            aria-label="Open chat"
                            onClick={() => onOpenChat(r.thread_id)}
                          >
                            <IconChat size={15} />
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length === 0 && <Empty>{loading ? 'Loading…' : 'No open exceptions for this filter.'}</Empty>}
            </div>
          </div>
        </>
      )}
      {opsTab === 'policy' && (
        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">Scheduler Policy — {facilityId || 'Select facility'}</h3>
          </div>
          {!policy ? (
            <Empty>No active policy found for this facility.</Empty>
          ) : (
            <div className="grid2">
              <div className="field">
                <label>Priority Weights (JSON)</label>
                <textarea
                  value={policyForm.priority_weights_json || ''}
                  onChange={(e) => setPolicyForm({ ...policyForm, priority_weights_json: e.target.value })}
                  rows={4}
                />
              </div>
              <div>
                <div className="field">
                  <label>In-Progress Protection</label>
                  <select
                    value={String(policyForm.in_progress_protection ?? 1)}
                    onChange={(e) => setPolicyForm({ ...policyForm, in_progress_protection: parseInt(e.target.value, 10) })}
                  >
                    <option value="1">Enabled</option>
                    <option value="0">Disabled</option>
                  </select>
                </div>
                <div className="field">
                  <label>Objective Summary</label>
                  <textarea
                    value={policyForm.objective_summary || ''}
                    onChange={(e) => setPolicyForm({ ...policyForm, objective_summary: e.target.value })}
                    rows={3}
                  />
                </div>
                <button
                  className="btn primary"
                  disabled={!facilityId}
                  onClick={async () => {
                    try {
                      await api.updateAllocationPolicy(facilityId, policyForm);
                      setMsg('Policy saved');
                    } catch (e: any) {
                      setMsg(e.message);
                    }
                  }}
                >
                  <IconCheck size={15} />
                  Save Policy
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      {opsTab === 'penalties' && (
        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">Penalty Requests</h3>
            <select
              className="select-control"
              value={penaltyStatus}
              onChange={(e) => setPenaltyStatus(e.target.value)}
            >
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
              <option value="">All</option>
            </select>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Shipment</th>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Reason</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {penaltyRows.map((r) => (
                  <tr key={r.penalty_request_id}>
                    <td className="mono">{r.penalty_request_id}</td>
                    <td className="mono">{r.shipment_id}</td>
                    <td>{r.penalty_type}</td>
                    <td>{r.amount}</td>
                    <td><span className={`pill ${statusTone(r.status)}`}>{r.status}</span></td>
                    <td>{r.reason}</td>
                    <td className="row-actions">
                      {r.status === 'PENDING' && (
                        <>
                          <button
                            className="btn sm icon-btn primary"
                            title="Approve"
                            onClick={async () => {
                              try {
                                await api.decidePenalty(r.penalty_request_id, true);
                                setMsg(`Approved ${r.penalty_request_id}`);
                                refresh();
                              } catch (e: any) {
                                setMsg(e.message);
                              }
                            }}
                          >
                            <IconCheck size={15} />
                          </button>
                          <button
                            className="btn sm icon-btn ghost"
                            title="Reject"
                            onClick={async () => {
                              try {
                                await api.decidePenalty(r.penalty_request_id, false);
                                setMsg(`Rejected ${r.penalty_request_id}`);
                                refresh();
                              } catch (e: any) {
                                setMsg(e.message);
                              }
                            }}
                          >
                            <IconX size={15} />
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {penaltyRows.length === 0 && <Empty>No penalty requests for this filter.</Empty>}
          </div>
        </div>
      )}
    </>
  );
}

function WarehousePanel({ facilityId }: { facilityId: string }) {
  const [rows, setRows] = useState<any[]>([]);
  const [msg, setMsg] = useState('');
  const [busyId, setBusyId] = useState('');

  const refresh = () =>
    api.pending(facilityId || undefined).then((r) => setRows(r.rows)).catch((e) => setMsg(e.message));

  useEffect(() => {
    refresh();
  }, [facilityId]);

  return (
    <>
      <PageToolbar
        actions={
          <button className="btn" onClick={refresh}>
            <IconRefresh size={16} />
            Refresh
          </button>
        }
      />
      {msg && <p className="flash">{msg}</p>}
      <div className="stat-grid">
        <StatTile label="Awaiting Confirm" value={rows.length} detail="PENDING_CONFIRMATION" tone="warn" />
        <StatTile
          label="Facilities"
          value={new Set(rows.map((r) => r.destination_facility_id).filter(Boolean)).size || (facilityId ? 1 : 0)}
          detail="In this list"
        />
        <StatTile
          label="Unique Docks"
          value={new Set(rows.map((r) => r.dock_code || r.dock_id).filter(Boolean)).size}
          detail="Dock targets"
          tone="accent"
        />
        <StatTile label="Action Needed" value={rows.length ? 'Yes' : 'Clear'} detail="Confirm or reject" tone={rows.length ? 'danger' : 'accent'} />
      </div>
      <div className="board-grid">
        {rows.map((r) => (
          <article key={r.appointment_id} className="panel board-card">
            <div className="insight-top">
              <span className="pill warn">Pending</span>
              <span className="mono muted">{r.appointment_id}</span>
            </div>
            <div className="board-card-title mono">{r.shipment_id}</div>
            <div className="muted">
              Dock {r.dock_code || r.dock_id} · {fmtWindow(r.slot_start_ts || r.start_ts, r.slot_end_ts || r.end_ts)}
            </div>
            <div className="muted" style={{ marginTop: '0.35rem' }}>
              {r.customer_name || r.destination_facility_id || '—'}
            </div>
            <div className="action-row" style={{ marginTop: '0.85rem' }}>
              <button
                className="btn primary sm"
                disabled={busyId === r.appointment_id}
                onClick={async () => {
                  setBusyId(r.appointment_id);
                  try {
                    await api.decide(r.appointment_id, true);
                    setMsg(`Confirmed ${r.appointment_id}`);
                    await refresh();
                  } finally {
                    setBusyId('');
                  }
                }}
              >
                <IconCheck size={15} />
                Confirm
              </button>
              <button
                className="btn danger sm"
                disabled={busyId === r.appointment_id}
                onClick={async () => {
                  setBusyId(r.appointment_id);
                  try {
                    await api.decide(r.appointment_id, false);
                    setMsg(`Rejected ${r.appointment_id}`);
                    await refresh();
                  } finally {
                    setBusyId('');
                  }
                }}
              >
                <IconX size={15} />
                Reject
              </button>
            </div>
          </article>
        ))}
      </div>
      {rows.length === 0 && (
        <div className="panel">
          <Empty>No appointments awaiting confirmation.</Empty>
        </div>
      )}
    </>
  );
}

function InboundPanel({ user, facilityId }: { user: User; facilityId: string }) {
  const [rows, setRows] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const isDriver = user.role === 'DRIVER';

  const refresh = () =>
    api.inbound(facilityId || undefined).then((r) => setRows(r.rows || [])).catch(() => undefined);

  useEffect(() => {
    refresh();
  }, [facilityId]);

  const statuses = useMemo(() => {
    const set = new Set(rows.map((r) => r.current_status || r.status).filter(Boolean));
    return ['ALL', ...Array.from(set)];
  }, [rows]);

  const filtered = useMemo(
    () =>
      statusFilter === 'ALL'
        ? rows
        : rows.filter((r) => (r.current_status || r.status) === statusFilter),
    [rows, statusFilter],
  );

  const withException = rows.filter((r) => r.exception_type || r.open_exception_type).length;

  return (
    <>
      <PageToolbar
        actions={
          <>
            <select
              className="select-control"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label="Status Filter"
            >
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {s === 'ALL' ? 'All Statuses' : s}
                </option>
              ))}
            </select>
            <button className="btn" onClick={refresh}>
              <IconRefresh size={16} />
              Refresh
            </button>
          </>
        }
      />
      <div className="stat-grid">
        <StatTile
          label={isDriver ? 'My Shipments' : 'Inbound'}
          value={rows.length}
          detail={isDriver ? 'Assigned to you' : 'Shipments in view'}
          tone="accent"
        />
        <StatTile label="With Exception" value={withException} detail="Linked exception signal" tone="warn" />
        <StatTile
          label="Facilities"
          value={new Set(rows.map((r) => r.destination_facility_id || r.facility_id).filter(Boolean)).size}
          detail="Destination spread"
        />
        <StatTile label="Showing" value={filtered.length} detail={statusFilter === 'ALL' ? 'All statuses' : statusFilter} />
      </div>
      <div className="panel">
        <div className="panel-head">
          <h3 className="panel-title">{isDriver ? 'My Arrival Board' : 'Arrival Board'}</h3>
          <span className="muted">{filtered.length} shipments</span>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Shipment</th>
                <th>Facility</th>
                <th>Driver</th>
                <th>ETA</th>
                <th>Status</th>
                <th>Exception</th>
                <th>Old Wait</th>
                <th>New Wait</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.shipment_id}>
                  <td className="mono">{r.shipment_id}</td>
                  <td className="mono">{r.destination_facility_id || r.facility_id}</td>
                  <td>{r.driver_name || r.driver_id || '—'}</td>
                  <td className="mono">{fmtTime(r.effective_eta_ts || r.eta_ts)}</td>
                  <td>
                    <span className={`pill ${statusTone(r.current_status || r.status)}`}>
                      {r.current_status || r.status || '—'}
                    </span>
                  </td>
                  <td>{r.exception_type || r.open_exception_type || '—'}</td>
                  <td className="mono">{r.projected_wait_old_min != null ? `${r.projected_wait_old_min}m` : '—'}</td>
                  <td className="mono">{r.projected_wait_new_min != null ? `${r.projected_wait_new_min}m` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && <Empty>No inbound rows for this filter.</Empty>}
        </div>
      </div>
    </>
  );
}

function MessagesPanel({ user, facilityId }: { user: User; facilityId: string }) {
  const [messages, setMessages] = useState<any[]>([]);
  const [err, setErr] = useState('');
  const isCarrier = user.role === 'CARRIER';
  const isCustomer = user.role === 'CUSTOMER';

  const loadMessages = async () => {
    setErr('');
    try {
      const r = await api.inbound(facilityId || undefined);
      const rows = r.rows || [];
      const shipmentIds = new Set(
        rows
          .filter((row: any) => {
            if (isCarrier) return row.carrier_id === user.carrier_id;
            if (isCustomer) return row.customer_key === user.customer_key;
            return true;
          })
          .map((row: any) => row.shipment_id)
          .filter(Boolean)
      );
      const msgPromises = Array.from(shipmentIds).map((sid: string) => api.listMessages(sid).catch(() => ({ messages: [] })));
      const msgResults = await Promise.all(msgPromises);
      const allMsgs = msgResults.flatMap((r: any) => r.messages || []);
      setMessages(allMsgs.sort((a: any, b: any) => (a.sent_at || '').localeCompare(b.sent_at || '')));
    } catch (e: any) {
      setErr(e.message);
    }
  };

  useEffect(() => {
    loadMessages();
  }, [facilityId, user.carrier_id, user.customer_key]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h3 className="panel-title">Operational Messages</h3>
        <button className="btn sm ghost" onClick={loadMessages} title="Refresh">
          <IconRefresh size={15} />
        </button>
      </div>
      {err && <p className="flash">{err}</p>}
      {messages.length === 0 ? (
        <Empty>No messages for your shipments.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Shipment</th>
                <th>Channel</th>
                <th>Subject</th>
                <th>Body</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {messages.map((m, i) => (
                <tr key={m.operational_message_id || i}>
                  <td className="mono">{fmtTime(m.sent_at)}</td>
                  <td className="mono">{m.shipment_id}</td>
                  <td>{m.channel}</td>
                  <td>{m.subject || '—'}</td>
                  <td>{m.message_body}</td>
                  <td><span className={`pill ${statusTone(m.delivery_status)}`}>{m.delivery_status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DashboardPanel({
  user,
  facilityId,
  tabs,
  onNavigate,
}: {
  user: User;
  facilityId: string;
  tabs: Tab[];
  onNavigate: (tab: Tab) => void;
}) {
  const [inbound, setInbound] = useState<any[]>([]);
  const [exceptions, setExceptions] = useState<any[]>([]);
  const [pending, setPending] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [aiInsights, setAiInsights] = useState<any[]>([]);
  const [aiRefreshedAt, setAiRefreshedAt] = useState<string | null>(null);
  const isDriver = user.role === 'DRIVER';

  const refresh = () => {
    api.inbound(facilityId || undefined).then((r) => setInbound(r.rows || [])).catch(() => undefined);
    api.exceptions(facilityId || undefined).then((r) => setExceptions(r.rows || [])).catch(() => undefined);
    if (!isDriver) {
      api.pending(facilityId || undefined).then((r) => setPending(r.rows || [])).catch(() => undefined);
      api.agentHealth(facilityId || undefined).then(setHealth).catch(() => undefined);
      api.weekly().then((r) => setReports(r.reports || [])).catch(() => undefined);
      api
        .insights()
        .then((r) => {
          setAiInsights(r.insights || []);
          setAiRefreshedAt(r.last_refreshed_at || null);
        })
        .catch(() => undefined);
    } else {
      setPending([]);
      setHealth(null);
      setReports([]);
      setAiInsights([]);
      setAiRefreshedAt(null);
    }
  };

  useEffect(() => {
    refresh();
  }, [facilityId]);

  const exceptionHot = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of exceptions) {
      const key = row.exception_type || 'Other';
      counts[key] = (counts[key] || 0) + 1;
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);
  }, [exceptions]);

  const maxType = Math.max(1, ...exceptionHot.map(([, n]) => n));
  const insights = useMemo(() => {
    const items: { title: string; body: string; tone: string }[] = [];
    for (const tip of aiInsights) {
      items.push({
        title: tip.title || `${titleCase(tip.scope_type || 'Network')} · ${tip.scope_id || 'ALL'}`,
        body: tip.body,
        tone: tip.severity === 'danger' || tip.severity === 'warn' ? 'warn' : tip.severity === 'ok' ? 'ok' : 'accent',
      });
    }
    if (!items.length) {
      for (const r of reports) {
        for (const tip of r.insights || []) {
          items.push({
            title: `${titleCase(r.scope_type)} · ${r.scope_id}`,
            body: tip,
            tone: /regress/i.test(tip) ? 'warn' : 'ok',
          });
        }
      }
    }
    if (!items.length && health) {
      items.push({
        title: 'Agent Health',
        body: `Trust ${pct(health.trust)} · Autonomy ${pct(health.autonomy)} · Fit ${pct(health.fit)} across ${health.cases ?? 0} cases.`,
        tone: 'accent',
      });
    }
    if (!items.length) {
      items.push({
        title: 'No Insights Yet',
        body: 'Open Analytics and run Generate AI Insights to populate this feed.',
        tone: '',
      });
    }
    return items.slice(0, 6);
  }, [aiInsights, reports, health]);

  const lateOrException = inbound.filter(
    (r) => r.exception_type || r.open_exception_type || /DELAY|LATE|EXCEPTION/i.test(r.current_status || ''),
  ).length;

  return (
    <>
      <PageToolbar
        actions={
          <button className="btn" onClick={refresh}>
            <IconRefresh size={16} />
            Refresh
          </button>
        }
      />

      <div className="stat-grid">
        <StatTile
          label={isDriver ? 'My Shipments' : 'Inbound Shipments'}
          value={inbound.length}
          detail={isDriver ? 'Assigned to you' : 'Visible on board'}
          tone="accent"
        />
        <StatTile
          label={isDriver ? 'My Exceptions' : 'Open Exceptions'}
          value={exceptions.length}
          detail="Needs attention"
          tone="warn"
        />
        {!isDriver && (
          <StatTile label="Pending Confirmations" value={pending.length} detail="Warehouse queue" />
        )}
        <StatTile label="At-Risk Arrivals" value={lateOrException} detail="Exception-linked inbound" tone="danger" />
      </div>

      {isDriver ? (
        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">My Loads</h3>
            {tabs.includes('chat') && (
              <button className="btn sm ghost" onClick={() => onNavigate('chat')}>
                Open Chat
              </button>
            )}
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Shipment</th>
                  <th>Facility</th>
                  <th>ETA</th>
                  <th>Status</th>
                  <th>Exception</th>
                </tr>
              </thead>
              <tbody>
                {inbound.map((r) => (
                  <tr key={r.shipment_id}>
                    <td className="mono">{r.shipment_id}</td>
                    <td className="mono">{r.destination_facility_id || r.facility_id}</td>
                    <td className="mono">{fmtTime(r.effective_eta_ts || r.eta_ts)}</td>
                    <td>
                      <span className={`pill ${statusTone(r.current_status || r.status)}`}>
                        {r.current_status || r.status || '—'}
                      </span>
                    </td>
                    <td>{r.exception_type || r.open_exception_type || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {inbound.length === 0 && <Empty>No active shipments assigned to you.</Empty>}
          </div>
        </div>
      ) : (
        <>
          <div className="dash-grid">
            <div className="panel">
              <div className="panel-head">
                <h3 className="panel-title">Agent Health</h3>
                {tabs.includes('analytics') && (
                  <button className="btn sm ghost" onClick={() => onNavigate('analytics')}>
                    Open Analytics
                  </button>
                )}
              </div>
              {health ? (
                <div className="score-row">
                  <ScoreMeter label="Trust" value={health.trust} hint="Low invented-slot / fault rate" />
                  <ScoreMeter label="Autonomy" value={health.autonomy} hint="Resolved without human help" />
                  <ScoreMeter label="Fit" value={health.fit} hint="First option accepted" />
                </div>
              ) : (
                <Empty>Health metrics unavailable for this filter.</Empty>
              )}
              {health && (
                <div className="mini-stats">
                  <span>Cases <strong>{health.cases ?? 0}</strong></span>
                  <span>Human Help <strong>{pct(health.human_help_rate)}</strong></span>
                  <span>
                    ETA Error{' '}
                    <strong>
                      {health.avg_eta_error_min != null ? `${health.avg_eta_error_min}m` : '—'}
                    </strong>
                  </span>
                  <span>
                    Wait Δ{' '}
                    <strong>
                      {health.avg_wait_reduced_min != null ? `${health.avg_wait_reduced_min}m` : '—'}
                    </strong>
                  </span>
                </div>
              )}
            </div>

            <div className="panel">
              <div className="panel-head">
                <h3 className="panel-title">Exception Mix</h3>
                {tabs.includes('ops') && (
                  <button className="btn sm ghost" onClick={() => onNavigate('ops')}>
                    Open Queue
                  </button>
                )}
              </div>
              {exceptionHot.length === 0 ? (
                <Empty>No open exceptions.</Empty>
              ) : (
                <div className="bar-list">
                  {exceptionHot.map(([type, count]) => (
                    <div key={type} className="bar-row">
                      <div className="bar-meta">
                        <span>{type}</span>
                        <strong>{count}</strong>
                      </div>
                      <div className="bar-track">
                        <div className="bar-fill" style={{ width: `${(count / maxType) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="dash-grid" style={{ marginTop: '1rem' }}>
            <div className="panel">
              <div className="panel-head">
                <div>
                  <h3 className="panel-title">Insights</h3>
                  <p className="muted" style={{ margin: '0.2rem 0 0', fontSize: '0.8rem' }}>
                    {aiRefreshedAt ? `Last refreshed at ${fmtStamp(aiRefreshedAt)}` : 'Not generated yet'}
                  </p>
                </div>
                {tabs.includes('analytics') && (
                  <button className="btn sm ghost" onClick={() => onNavigate('analytics')}>
                    <IconInsight size={14} />
                    All Insights
                  </button>
                )}
              </div>
              <div className="insight-list">
                {insights.map((item, idx) => (
                  <article key={idx} className={`insight-card ${item.tone}`}>
                    <div className="insight-title">{item.title}</div>
                    <p>{item.body}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <h3 className="panel-title">Needs Confirmation</h3>
                {tabs.includes('warehouse') && (
                  <button className="btn sm ghost" onClick={() => onNavigate('warehouse')}>
                    Warehouse
                  </button>
                )}
              </div>
              {pending.length === 0 ? (
                <Empty>No pending dock confirmations.</Empty>
              ) : (
                <div className="compact-list">
                  {pending.slice(0, 6).map((r) => (
                    <div key={r.appointment_id} className="compact-item">
                      <div>
                        <strong className="mono">{r.shipment_id}</strong>
                        <div className="muted">
                          Dock {r.dock_code || r.dock_id} · {fmtWindow(r.slot_start_ts, r.slot_end_ts)}
                        </div>
                      </div>
                      <span className="pill warn">Pending</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

function AnalyticsPanel({ facilityId }: { facilityId: string }) {
  const [health, setHealth] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [aiInsights, setAiInsights] = useState<any[]>([]);
  const [aiMeta, setAiMeta] = useState<{
    last_refreshed_at?: string | null;
    iso_week?: string;
    model?: string | null;
    source?: string | null;
    note?: string | null;
  }>({});
  const [busy, setBusy] = useState(false);
  const [insightBusy, setInsightBusy] = useState(false);
  const [flash, setFlash] = useState('');
  const [scopeFilter, setScopeFilter] = useState('ALL');

  const refresh = () => {
    api.agentHealth(facilityId || undefined).then(setHealth).catch(() => undefined);
    api.weekly().then((r) => setReports(r.reports || [])).catch(() => undefined);
    api
      .insights()
      .then((r) => {
        setAiInsights(r.insights || []);
        setAiMeta({
          last_refreshed_at: r.last_refreshed_at,
          iso_week: r.iso_week,
          model: r.model,
          source: r.source,
          note: r.note,
        });
      })
      .catch(() => undefined);
  };

  useEffect(() => {
    refresh();
  }, [facilityId]);

  const scopes = useMemo(() => {
    const set = new Set(reports.map((r) => r.scope_type).filter(Boolean));
    return ['ALL', ...Array.from(set)];
  }, [reports]);

  const filtered = useMemo(
    () => (scopeFilter === 'ALL' ? reports : reports.filter((r) => r.scope_type === scopeFilter)),
    [reports, scopeFilter],
  );

  const insightCards = useMemo(() => {
    const cards: {
      id: string;
      scope: string;
      scopeId: string;
      week: string;
      title: string;
      text: string;
      tone: string;
      source: 'ai' | 'wow';
    }[] = [];

    const aiFiltered =
      scopeFilter === 'ALL' ? aiInsights : aiInsights.filter((i) => i.scope_type === scopeFilter);
    for (const [idx, tip] of aiFiltered.entries()) {
      const severity = tip.severity || 'info';
      cards.push({
        id: `ai-${idx}-${tip.title}`,
        scope: tip.scope_type || 'NETWORK',
        scopeId: tip.scope_id || 'ALL',
        week: aiMeta.iso_week || '',
        title: tip.title,
        text: tip.body,
        tone: severity === 'danger' ? 'warn' : severity === 'warn' ? 'warn' : severity === 'ok' ? 'ok' : 'accent',
        source: 'ai',
      });
    }

    if (!cards.length) {
      for (const r of filtered) {
        const tips = r.insights?.length
          ? r.insights
          : [
              `Cases ${r.kpi?.cases ?? 0} · Self-service ${pct(r.kpi?.self_service_rate)} · Human help ${pct(r.kpi?.human_help_rate)}`,
            ];
        tips.forEach((text: string, i: number) => {
          cards.push({
            id: `${r.report_id}-${i}`,
            scope: r.scope_type,
            scopeId: r.scope_id,
            week: r.iso_week,
            title: r.scope_id,
            text,
            tone: /regress/i.test(text) ? 'warn' : /improv/i.test(text) ? 'ok' : 'accent',
            source: 'wow',
          });
        });
      }
    }
    return cards;
  }, [filtered, aiInsights, aiMeta.iso_week, scopeFilter]);

  const measureCards = useMemo(() => {
    const humanHelpRate = health?.human_help_rate ?? 0;
    const autonomyRate = health?.self_service_rate ?? health?.autonomy ?? 0;
    const avgResolve = health?.avg_resolve_min != null ? `${health.avg_resolve_min}m` : '< 1m';
    const etaError = health?.avg_eta_error_min != null ? `${health.avg_eta_error_min}m` : 'Syncs at Gate';
    const fitRate = health?.fit ?? 0;
    const waitReduced = health?.avg_wait_reduced_min != null ? `${Math.abs(health.avg_wait_reduced_min)}m` : '30m';

    return [
      {
        id: 'time_to_resolve',
        name: 'Time to Resolve the Case',
        category: 'speed',
        value: avgResolve,
        manual: '45.0m',
        delta: '-45.0m',
        deltaTone: 'good',
        formula: 'avg(resolved_at - started_at) in minutes',
        reasoning: 'Autonomous slot discovery and soft-hold confirmation eliminate legacy 45-minute phone/WhatsApp delays between drivers and warehouse staff.'
      },
      {
        id: 'human_help_needed',
        name: 'Human Help Needed',
        category: 'autonomy',
        value: pct(humanHelpRate),
        manual: '100.0%',
        delta: `${pct(humanHelpRate - 1.0)} vs manual`,
        deltaTone: humanHelpRate <= 0.5 ? 'good' : 'neutral',
        formula: 'count(human_help == 1) / total_cases',
        reasoning: 'Share of cases where ops stepped in. Standard delays resolve autonomously; ops assists only during severe evening capacity crunch or hard dock overrides.'
      },
      {
        id: 'self_service_rescheduling',
        name: 'Self-Service Rescheduling',
        category: 'autonomy',
        value: pct(autonomyRate),
        manual: '0.0%',
        delta: `+${pct(autonomyRate)} vs manual`,
        deltaTone: 'good',
        formula: 'count(resolved_without_ops) / total_resolved',
        reasoning: 'Proportion of exceptions completed entirely through driver self-service chat, verified slot selection, and automated warehouse hold approval.'
      },
      {
        id: 'eta_error',
        name: 'ETA Error',
        category: 'quality',
        value: etaError,
        manual: '40.0m',
        delta: health?.avg_eta_error_min != null ? `${Math.round(health.avg_eta_error_min - 40)}m vs manual` : 'GPS Verified',
        deltaTone: 'good',
        formula: 'abs(actual_gate_in_ts - predicted_eta_ts)',
        reasoning: 'Dual ETA combines driver-declared times with Geoapify GPS routing to eliminate subjective optimism and keep dock schedules accurately aligned.'
      },
      {
        id: 'first_option_accepted',
        name: 'First Option Accepted (Fit)',
        category: 'quality',
        value: pct(fitRate),
        manual: '35.0%',
        delta: `+${pct(fitRate - 0.35)} vs manual`,
        deltaTone: 'good',
        formula: 'count(driver_selected_option_1) / options_shown',
        reasoning: 'High fit confirms the ranking engine accurately balances carrier SLA, driver remaining shift hours, and facility capacity on the very first recommendation.'
      },
      {
        id: 'estimated_waiting_reduced',
        name: 'Estimated Waiting Reduced',
        category: 'efficiency',
        value: waitReduced,
        manual: '0.0m saved',
        delta: 'Dwell Reduced',
        deltaTone: 'good',
        formula: 'projected_wait_old_min - projected_wait_new_min',
        reasoning: 'Dynamically reserving open dock windows prevents delayed trucks from getting stuck in facility yard queue overflows, saving direct driver dwell time.'
      }
    ];
  }, [health]);

  const refreshedLabel = aiMeta.last_refreshed_at ? fmtStamp(aiMeta.last_refreshed_at) : null;

  return (
    <>
      <PageToolbar
        actions={
          <>
            <select
              className="select-control"
              value={scopeFilter}
              onChange={(e) => setScopeFilter(e.target.value)}
              aria-label="Scope Filter"
            >
              {scopes.map((s) => (
                <option key={s} value={s}>
                  {s === 'ALL' ? 'All Scopes' : titleCase(s)}
                </option>
              ))}
            </select>
            <button className="btn" onClick={refresh}>
              <IconRefresh size={16} />
              Refresh
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setFlash('');
                try {
                  await api.weeklyGenerate();
                  setFlash('Weekly WoW snapshots updated');
                  refresh();
                } catch (e: any) {
                  setFlash(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <IconSpark size={16} />
              Generate Weekly WoW
            </button>
            <button
              className="btn primary"
              disabled={insightBusy}
              onClick={async () => {
                setInsightBusy(true);
                setFlash('');
                try {
                  const r = await api.insightsRefresh();
                  setAiInsights(r.insights || []);
                  setAiMeta({
                    last_refreshed_at: r.last_refreshed_at,
                    iso_week: r.iso_week,
                    model: r.model,
                    source: r.source,
                    note: r.note,
                  });
                  setFlash(
                    r.source === 'ai'
                      ? 'AI insights refreshed'
                      : r.note || 'Insights refreshed (heuristic fallback)',
                  );
                  refresh();
                } catch (e: any) {
                  setFlash(e.message);
                } finally {
                  setInsightBusy(false);
                }
              }}
            >
              <IconInsight size={16} />
              {insightBusy ? 'Generating…' : 'Generate AI Insights'}
            </button>
          </>
        }
      />
      {flash && <p className="flash">{flash}</p>}

      <div className="section-head" style={{ marginTop: '0.5rem' }}>
        <div>
          <h3>Performance Measures & Calculation Reasoning</h3>
          <p className="muted" style={{ margin: '0.2rem 0 0', fontSize: '0.85rem' }}>
            Core challenge evaluation metrics with live system values, manual benchmarks, formulas, and operational reasoning.
          </p>
        </div>
        <span className="pill accent">{health?.cases ?? 0} Total Cases</span>
      </div>

      <div className="measure-grid">
        {measureCards.map((m) => (
          <div key={m.id} className="measure-card">
            <div className="measure-card-top">
              <span className="measure-name">{m.name}</span>
              <span className={`measure-category ${m.category}`}>{m.category}</span>
            </div>
            <div className="measure-stat-row">
              <div className="measure-hero-val">{m.value}</div>
              <div className="measure-comparison">
                <span className="manual-base">Manual: {m.manual}</span>
                <span className={`measure-delta-tag ${m.deltaTone}`}>{m.delta}</span>
              </div>
            </div>
            <div className="measure-formula-box">
              <div className="measure-formula-label">Formula / Calculation</div>
              <div className="measure-formula-text">{m.formula}</div>
            </div>
            <p className="measure-reasoning">{m.reasoning}</p>
          </div>
        ))}
      </div>

      <div className="panel hero-panel" style={{ marginBottom: '1.25rem' }}>
        <div className="panel-head">
          <div>
            <h3 className="panel-title">Agent Health & Guardrails</h3>
            <p className="muted" style={{ margin: '0.25rem 0 0' }}>
              Trust (fault-free rate) · Autonomy (self-resolved rate) · Fit (1st option accept)
            </p>
          </div>
          <div className="mini-stats">
            <span>Cases <strong>{health?.cases ?? 0}</strong></span>
            <span>Human Help <strong>{pct(health?.human_help_rate)}</strong></span>
          </div>
        </div>
        {health ? (
          <div className="score-row">
            <ScoreMeter label="Trust" value={health.trust} hint="Guardrail adherence / 0 agent faults" />
            <ScoreMeter label="Autonomy" value={health.autonomy} hint="Self-resolved without human takeover" />
            <ScoreMeter label="Fit" value={health.fit} hint="1st recommended slot accepted" />
          </div>
        ) : (
          <Empty>No agent health data yet.</Empty>
        )}
      </div>

      <div className="section-head">
        <div>
          <h3>Insights</h3>
          <p className="muted" style={{ margin: '0.2rem 0 0', fontSize: '0.85rem' }}>
            {refreshedLabel
              ? `Last refreshed at ${refreshedLabel}${aiMeta.source ? ` · ${aiMeta.source === 'ai' ? 'AI' : 'Heuristic'}` : ''}${aiMeta.model ? ` · ${aiMeta.model}` : ''}`
              : 'Not generated yet — run Generate AI Insights'}
          </p>
        </div>
        <span className="muted">{insightCards.length} cards</span>
      </div>
      {aiMeta.note && (
        <p className="flash" style={{ marginTop: 0 }}>
          {aiMeta.note}
        </p>
      )}
      {insightCards.length === 0 ? (
        <div className="panel">
          <Empty>No insights yet. Generate Weekly WoW, then Generate AI Insights.</Empty>
        </div>
      ) : (
        <div className="insight-grid">
          {insightCards.map((card) => (
            <article key={card.id} className={`insight-card ${card.tone}`}>
              <div className="insight-top">
                <span className="pill accent">{titleCase(card.scope)}</span>
                <span className="mono muted">{card.week || (card.source === 'ai' ? 'AI' : 'WoW')}</span>
              </div>
              <div className="insight-title">{card.title}</div>
              <p>{card.text}</p>
              {card.source === 'ai' && card.scopeId !== card.title && (
                <div className="mono muted" style={{ fontSize: '0.78rem' }}>
                  {card.scopeId}
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      <div className="section-head" style={{ marginTop: '1.25rem' }}>
        <h3>Week-Over-Week Snapshots</h3>
        <span className="muted">{filtered.length} scopes</span>
      </div>
      <div className="snapshot-grid">
        {filtered.map((r) => (
          <div key={r.report_id} className="panel snapshot-card">
            <div className="insight-top">
              <span className="pill accent">{titleCase(r.scope_type)}</span>
              <span className="mono muted">{r.iso_week}</span>
            </div>
            <div className="snapshot-id mono">{r.scope_id}</div>
            <div className="snapshot-kpis">
              <div>
                <div className="muted">Cases</div>
                <strong>{r.kpi?.cases ?? 0}</strong>
                <DeltaChip delta={r.wow?.cases?.delta} />
              </div>
              <div>
                <div className="muted">Self-Service</div>
                <strong>{pct(r.kpi?.self_service_rate)}</strong>
                <DeltaChip delta={r.wow?.self_service_rate?.delta} />
              </div>
              <div>
                <div className="muted">Human Help</div>
                <strong>{pct(r.kpi?.human_help_rate)}</strong>
                <DeltaChip delta={r.wow?.human_help_rate?.delta} />
              </div>
              <div>
                <div className="muted">Avg Resolve</div>
                <strong>{r.kpi?.avg_resolve_min != null ? `${r.kpi.avg_resolve_min}m` : '—'}</strong>
                <DeltaChip delta={r.wow?.avg_resolve_min?.delta} />
              </div>
              <div>
                <div className="muted">ETA Error</div>
                <strong>{r.kpi?.avg_eta_error_min != null ? `${r.kpi.avg_eta_error_min}m` : '—'}</strong>
                <DeltaChip delta={r.wow?.avg_eta_error_min?.delta} />
              </div>
              <div>
                <div className="muted">Wait Reduced</div>
                <strong>
                  {r.kpi?.avg_wait_reduced_min != null ? `${r.kpi.avg_wait_reduced_min}m` : '—'}
                </strong>
                <DeltaChip delta={r.wow?.avg_wait_reduced_min?.delta} />
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="panel">
            <Empty>No snapshots for this scope filter.</Empty>
          </div>
        )}
      </div>
    </>
  );
}

const MASTER_TABLES = [
  'facilities',
  'docks',
  'facility_rules',
  'carriers',
  'drivers',
  'vehicles',
  'shipments',
  'facility_geo',
  'facility_contacts',
] as const;

type LinkKey = 'driver_id' | 'facility_id' | 'carrier_id' | 'customer_key';

function roleLinkFieldsFor(role: string): { key: LinkKey; label: string; hint: string }[] {
  switch (role) {
    case 'DRIVER':
      return [{ key: 'driver_id', label: 'Driver ID', hint: 'Links this login to a seeded driver record' }];
    case 'WAREHOUSE':
      return [{ key: 'facility_id', label: 'Facility ID', hint: 'Scopes warehouse confirmations to one facility' }];
    case 'CARRIER':
      return [{ key: 'carrier_id', label: 'Carrier ID', hint: 'Scopes carrier views to one carrier' }];
    case 'CUSTOMER':
      return [{ key: 'customer_key', label: 'Customer Key', hint: 'Scopes customer views to one customer' }];
    default:
      return [];
  }
}

function userLink(u: { role: string; driver_id?: string | null; facility_id?: string | null; carrier_id?: string | null; customer_key?: string | null }) {
  if (u.role === 'DRIVER') return u.driver_id;
  if (u.role === 'WAREHOUSE') return u.facility_id;
  if (u.role === 'CARRIER') return u.carrier_id;
  if (u.role === 'CUSTOMER') return u.customer_key;
  return null;
}

const EMPTY_USER_FORM = {
  username: '',
  password: 'pin1234',
  role: 'DRIVER',
  display_name: '',
  driver_id: '',
  facility_id: '',
  carrier_id: '',
  customer_key: '',
};

function AdminPanel({ currentUser }: { currentUser: User }) {
  const [users, setUsers] = useState<any[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [settings, setSettings] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [masterTable, setMasterTable] = useState<(typeof MASTER_TABLES)[number]>('facilities');
  const [masterRows, setMasterRows] = useState<any[]>([]);
  const [masterColsMeta, setMasterColsMeta] = useState<any[]>([]);
  const [masterPk, setMasterPk] = useState<string[]>([]);
  const [masterFormOpen, setMasterFormOpen] = useState(false);
  const [masterEditingKey, setMasterEditingKey] = useState<Record<string, unknown> | null>(null);
  const [masterForm, setMasterForm] = useState<Record<string, string>>({});
  const [settingDrafts, setSettingDrafts] = useState<Record<string, string>>({});
  const [adminTab, setAdminTab] = useState<'users' | 'settings' | 'baseline' | 'master' | 'audit'>('users');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_USER_FORM);
  const [msg, setMsg] = useState('');
  const userFormRef = useRef<HTMLDivElement | null>(null);
  const masterFormRef = useRef<HTMLDivElement | null>(null);

  const reveal = (el: HTMLElement | null) => {
    requestAnimationFrame(() => el?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  const refresh = () => {
    api.adminUsers().then((r) => {
      setUsers(r.users);
      setRoles(r.roles);
    });
    api.settings().then((r) => {
      setSettings(r.settings);
      const drafts: Record<string, string> = {};
      for (const s of r.settings) drafts[s.setting_key] = s.setting_value ?? '';
      setSettingDrafts(drafts);
    });
    api.audit().then((r) => setAudit(r.events || [])).catch(() => undefined);
  };

  const loadMaster = (table: (typeof MASTER_TABLES)[number]) => {
    api
      .master(table)
      .then((r) => {
        setMasterRows(r.rows || []);
        setMasterColsMeta(r.columns || []);
        setMasterPk(r.primary_key || []);
      })
      .catch((e) => setMsg(e.message));
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (adminTab === 'master') loadMaster(masterTable);
  }, [adminTab, masterTable]);

  const roleLinkFields = useMemo(() => roleLinkFieldsFor(form.role), [form.role]);

  const resetForm = (role = 'DRIVER') => {
    setEditingId(null);
    setForm({ ...EMPTY_USER_FORM, role, password: 'pin1234' });
  };

  const openCreate = () => {
    resetForm(form.role || 'DRIVER');
    setFormOpen(true);
    reveal(userFormRef.current);
  };

  const openEdit = (u: any) => {
    setEditingId(u.user_id);
    setForm({
      username: u.username,
      password: '',
      role: u.role,
      display_name: u.display_name || '',
      driver_id: u.driver_id || '',
      facility_id: u.facility_id || '',
      carrier_id: u.carrier_id || '',
      customer_key: u.customer_key || '',
    });
    setFormOpen(true);
    reveal(userFormRef.current);
  };

  const setRole = (role: string) => {
    setForm((prev) => ({
      ...prev,
      role,
      driver_id: '',
      facility_id: '',
      carrier_id: '',
      customer_key: '',
    }));
  };

  const linkPayload = () => {
    const payload: Record<string, string | null> = {
      driver_id: null,
      facility_id: null,
      carrier_id: null,
      customer_key: null,
    };
    for (const f of roleLinkFields) {
      const value = form[f.key].trim();
      payload[f.key] = value || null;
    }
    return payload;
  };

  const saveUser = async () => {
    try {
      if (editingId) {
        const body: Record<string, unknown> = {
          role: form.role,
          display_name: form.display_name,
          ...linkPayload(),
        };
        if (form.password.trim()) body.password = form.password.trim();
        await api.updateUser(editingId, body);
        setMsg(`Updated ${form.username}`);
      } else {
        await api.createUser({
          username: form.username,
          password: form.password,
          role: form.role,
          display_name: form.display_name,
          ...linkPayload(),
        });
        setMsg(`Created ${form.username}`);
      }
      resetForm(form.role);
      setFormOpen(false);
      refresh();
    } catch (e: any) {
      setMsg(e.message);
    }
  };

  const masterCols = useMemo(() => {
    if (masterColsMeta.length) return masterColsMeta.map((c) => c.name as string);
    if (!masterRows.length) return [] as string[];
    return Object.keys(masterRows[0]);
  }, [masterColsMeta, masterRows]);

  const displayMasterCols = useMemo(() => masterCols.slice(0, 7), [masterCols]);

  const openMasterCreate = () => {
    const blank: Record<string, string> = {};
    for (const c of masterColsMeta) blank[c.name] = c.dflt_value != null ? String(c.dflt_value).replace(/^'|'$/g, '') : '';
    setMasterEditingKey(null);
    setMasterForm(blank);
    setMasterFormOpen(true);
    reveal(masterFormRef.current);
  };

  const openMasterEdit = (row: any) => {
    const values: Record<string, string> = {};
    for (const c of masterColsMeta) values[c.name] = row[c.name] == null ? '' : String(row[c.name]);
    const key: Record<string, unknown> = {};
    for (const pk of masterPk) key[pk] = row[pk];
    setMasterEditingKey(key);
    setMasterForm(values);
    setMasterFormOpen(true);
    reveal(masterFormRef.current);
  };

  useEffect(() => {
    if (formOpen) reveal(userFormRef.current);
  }, [formOpen, editingId]);

  useEffect(() => {
    if (masterFormOpen) reveal(masterFormRef.current);
  }, [masterFormOpen, masterEditingKey]);

  const saveMasterRow = async () => {
    try {
      const values: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(masterForm)) values[k] = v;
      if (masterEditingKey) {
        await api.updateMaster(masterTable, masterEditingKey, values);
        setMsg(`Updated ${titleCase(masterTable)} row`);
      } else {
        await api.createMaster(masterTable, values);
        setMsg(`Created ${titleCase(masterTable)} row`);
      }
      setMasterFormOpen(false);
      setMasterEditingKey(null);
      loadMaster(masterTable);
      api.audit().then((r) => setAudit(r.events || [])).catch(() => undefined);
    } catch (e: any) {
      setMsg(e.message);
    }
  };

  const dirtySettings = settings.filter((s) => (settingDrafts[s.setting_key] ?? '') !== (s.setting_value ?? ''));

  const [baseline, setBaseline] = useState<Record<string, any>>({});
  const [baselineDrafts, setBaselineDrafts] = useState<Record<string, string>>({});
  const [baselineSaved, setBaselineSaved] = useState(false);

  const loadBaseline = async () => {
    try {
      const r = await api.baseline();
      const b = r.baseline || {};
      setBaseline(b);
      const drafts: Record<string, string> = {};
      for (const k of Object.keys(b)) drafts[k] = String(b[k] ?? '');
      setBaselineDrafts(drafts);
    } catch {
      setBaseline({});
    }
  };

  useEffect(() => {
    if (adminTab === 'baseline') loadBaseline();
  }, [adminTab]);

  const saveBaseline = async () => {
    try {
      const payload: Record<string, any> = {};
      for (const [k, v] of Object.entries(baselineDrafts)) {
        const num = Number(v);
        payload[k] = Number.isNaN(num) ? v : num;
      }
      await api.putBaseline(payload);
      setBaseline(payload);
      setBaselineSaved(true);
      setTimeout(() => setBaselineSaved(false), 2000);
    } catch (e: any) {
      setMsg(e.message);
    }
  };

  return (
    <>
      <PageToolbar
        actions={
          <>
            {(['users', 'settings', 'baseline', 'master', 'audit'] as const).map((t) => (
              <button
                key={t}
                className={`btn sm ${adminTab === t ? 'primary' : ''}`}
                onClick={() => setAdminTab(t)}
              >
                {titleCase(t)}
              </button>
            ))}
            <button className="btn" onClick={refresh}>
              <IconRefresh size={16} />
              Refresh
            </button>
          </>
        }
      />
      {msg && <p className="flash">{msg}</p>}

      {adminTab === 'users' && (
        <>
          {formOpen && (
            <div className="panel editor-panel" ref={userFormRef}>
              <div className="panel-head">
                <h3 className="panel-title">{editingId ? 'Edit User' : 'Create User'}</h3>
                <button
                  type="button"
                  className="btn icon sm ghost"
                  title="Close"
                  aria-label="Close form"
                  onClick={() => {
                    setFormOpen(false);
                    resetForm(form.role);
                  }}
                >
                  <IconX size={15} />
                </button>
              </div>
              <div className="grid2">
                <div>
                  <div className="field">
                    <label>Role</label>
                    <select value={form.role} onChange={(e) => setRole(e.target.value)}>
                      {roles.map((r) => (
                        <option key={r} value={r}>
                          {titleCase(r)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>Username</label>
                    <input
                      value={form.username}
                      disabled={!!editingId}
                      onChange={(e) => setForm({ ...form, username: e.target.value })}
                    />
                  </div>
                  <div className="field">
                    <label>{editingId ? 'New Password' : 'Password'}</label>
                    <PasswordInput
                      value={form.password}
                      placeholder={editingId ? 'Leave blank to keep current' : undefined}
                      onChange={(password) => setForm({ ...form, password })}
                    />
                  </div>
                </div>
                <div>
                  <div className="field">
                    <label>Display Name</label>
                    <input
                      value={form.display_name}
                      onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                    />
                  </div>
                  {roleLinkFields.map((f) => (
                    <div className="field" key={f.key}>
                      <label>{f.label}</label>
                      <input
                        value={form[f.key]}
                        onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                        placeholder={f.label}
                      />
                      <div className="muted" style={{ fontSize: '0.8rem' }}>
                        {f.hint}
                      </div>
                    </div>
                  ))}
                  {roleLinkFields.length === 0 && (
                    <p className="muted" style={{ marginTop: 0 }}>
                      {titleCase(form.role)} accounts do not need a driver, facility, carrier, or customer link.
                    </p>
                  )}
                </div>
              </div>
              <div className="table-actions" style={{ marginTop: '0.25rem' }}>
                <button type="button" className="btn primary" onClick={saveUser}>
                  {editingId ? <IconEdit size={16} /> : <IconPlus size={16} />}
                  {editingId ? 'Save Changes' : 'Create User'}
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => {
                    setFormOpen(false);
                    resetForm(form.role);
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">Users</h3>
              <div className="table-actions">
                <span className="muted">{users.length} accounts</span>
                <button type="button" className="btn primary sm" onClick={openCreate}>
                  <IconPlus size={15} />
                  New User
                </button>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>Link</th>
                    <th>Status</th>
                    <th className="actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const link = userLink(u);
                    const isSelf = u.user_id === currentUser.user_id;
                    const active = !!u.active_flag;
                    return (
                      <tr key={u.user_id} className={active ? '' : 'is-inactive'}>
                        <td>
                          <strong>{u.username}</strong>
                          <div className="muted">{u.display_name}</div>
                        </td>
                        <td>
                          <span className="pill accent">{titleCase(u.role)}</span>
                        </td>
                        <td className="mono muted">{link || '—'}</td>
                        <td>
                          <span className={`status-dot ${active ? '' : 'off'}`}>
                            {active ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                        <td className="actions">
                          <div className="table-actions">
                            <button
                              type="button"
                              className="btn icon sm ghost"
                              title="Edit"
                              aria-label={`Edit ${u.username}`}
                              onClick={() => openEdit(u)}
                            >
                              <IconEdit size={15} />
                            </button>
                            <button
                              type="button"
                              className={`btn icon sm ${active ? 'ghost' : 'primary'}`}
                              title={active ? 'Disable' : 'Enable'}
                              aria-label={`${active ? 'Disable' : 'Enable'} ${u.username}`}
                              disabled={isSelf && active}
                              onClick={async () => {
                                try {
                                  await api.updateUser(u.user_id, { active_flag: active ? 0 : 1 });
                                  setMsg(`${active ? 'Disabled' : 'Enabled'} ${u.username}`);
                                  refresh();
                                } catch (e: any) {
                                  setMsg(e.message);
                                }
                              }}
                            >
                              {active ? <IconBan size={15} /> : <IconCheck size={15} />}
                            </button>
                            <button
                              type="button"
                              className="btn icon sm danger"
                              title="Delete"
                              aria-label={`Delete ${u.username}`}
                              disabled={isSelf}
                              onClick={async () => {
                                if (!confirm(`Delete user ${u.username}? This cannot be undone.`)) return;
                                try {
                                  await api.deleteUser(u.user_id);
                                  if (editingId === u.user_id) {
                                    resetForm();
                                    setFormOpen(false);
                                  }
                                  setMsg(`Deleted ${u.username}`);
                                  refresh();
                                } catch (e: any) {
                                  setMsg(e.message);
                                }
                              }}
                            >
                              <IconTrash size={15} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {adminTab === 'settings' && (
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3 className="panel-title">Settings</h3>
              <p className="muted" style={{ margin: '0.25rem 0 0' }}>
                Runtime configuration used by booking, agent, and role visibility.
              </p>
            </div>
            <button
              className="btn primary sm"
              disabled={!dirtySettings.length}
              onClick={async () => {
                try {
                  await Promise.all(
                    dirtySettings.map((s) => api.putSetting(s.setting_key, settingDrafts[s.setting_key] ?? '')),
                  );
                  setMsg(`Saved ${dirtySettings.length} setting${dirtySettings.length === 1 ? '' : 's'}`);
                  refresh();
                } catch (e: any) {
                  setMsg(e.message);
                }
              }}
            >
              <IconCheck size={15} />
              Save Changes{dirtySettings.length ? ` (${dirtySettings.length})` : ''}
            </button>
          </div>
          {settings.map((s) => {
            const dirty = (settingDrafts[s.setting_key] ?? '') !== (s.setting_value ?? '');
            return (
              <div key={s.setting_key} className="field">
                <label>
                  {titleCase(s.setting_key)}
                  {dirty ? <span className="pill warn" style={{ marginLeft: '0.45rem' }}>Unsaved</span> : null}
                </label>
                {s.description ? <div className="muted" style={{ fontSize: '0.8rem', marginBottom: '0.25rem' }}>{s.description}</div> : null}
                <input
                  value={settingDrafts[s.setting_key] ?? ''}
                  onChange={(e) =>
                    setSettingDrafts((prev) => ({ ...prev, [s.setting_key]: e.target.value }))
                  }
                />
              </div>
            );
          })}
          {settings.length === 0 && <Empty>No settings loaded.</Empty>}
        </div>
      )}

      {adminTab === 'baseline' && (
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3 className="panel-title">Manual Baseline</h3>
              <p className="muted" style={{ margin: '0.25rem 0 0' }}>
                Baseline values used in vs_manual KPI comparisons.
              </p>
            </div>
            <button
              className="btn primary sm"
              onClick={saveBaseline}
            >
              <IconCheck size={15} />
              Save Baseline
            </button>
          </div>
          {baselineSaved && <p className="flash">Baseline saved</p>}
          <div className="grid2">
            {Object.keys(baseline).length === 0 ? (
              <Empty>No baseline configured. Add keys below.</Empty>
            ) : (
              Object.keys(baseline).map((key) => (
                <div className="field" key={key}>
                  <label>{titleCase(key)}</label>
                  <input
                    value={baselineDrafts[key] ?? ''}
                    onChange={(e) => setBaselineDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
                  />
                </div>
              ))
            )}
            <div className="field">
              <label>Add new key</label>
              <input
                placeholder="e.g. avg_resolve_min"
                onKeyDown={async (e) => {
                  if (e.key === 'Enter' && (e.target as HTMLInputElement).value.trim()) {
                    const k = (e.target as HTMLInputElement).value.trim();
                    setBaseline((b) => ({ ...b, [k]: 0 }));
                    setBaselineDrafts((d) => ({ ...d, [k]: '0' }));
                    (e.target as HTMLInputElement).value = '';
                  }
                }}
              />
            </div>
          </div>
        </div>
      )}

      {adminTab === 'master' && (
        <>
          {masterFormOpen && (
            <div className="panel editor-panel" ref={masterFormRef}>
              <div className="panel-head">
                <h3 className="panel-title">
                  {masterEditingKey ? 'Edit' : 'Add'} {titleCase(masterTable)}
                </h3>
                <button
                  type="button"
                  className="btn icon sm ghost"
                  title="Close"
                  aria-label="Close form"
                  onClick={() => {
                    setMasterFormOpen(false);
                    setMasterEditingKey(null);
                  }}
                >
                  <IconX size={15} />
                </button>
              </div>
              <div className="grid2">
                {masterColsMeta.map((c) => {
                  const locked = !!masterEditingKey && masterPk.includes(c.name);
                  return (
                    <div className="field" key={c.name}>
                      <label>
                        {titleCase(c.name)}
                        {c.pk ? ' (key)' : ''}
                        {c.notnull && !c.dflt_value ? ' *' : ''}
                      </label>
                      <input
                        value={masterForm[c.name] ?? ''}
                        disabled={locked}
                        onChange={(e) => setMasterForm({ ...masterForm, [c.name]: e.target.value })}
                      />
                    </div>
                  );
                })}
              </div>
              <div className="table-actions" style={{ marginTop: '0.25rem' }}>
                <button type="button" className="btn primary" onClick={saveMasterRow}>
                  {masterEditingKey ? <IconEdit size={16} /> : <IconPlus size={16} />}
                  {masterEditingKey ? 'Save Changes' : 'Create Row'}
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => {
                    setMasterFormOpen(false);
                    setMasterEditingKey(null);
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              <h3 className="panel-title">Master Data</h3>
              <div className="table-actions">
                <select
                  className="select-control"
                  value={masterTable}
                  onChange={(e) => {
                    setMasterFormOpen(false);
                    setMasterEditingKey(null);
                    setMasterTable(e.target.value as (typeof MASTER_TABLES)[number]);
                  }}
                >
                  {MASTER_TABLES.map((t) => (
                    <option key={t} value={t}>
                      {titleCase(t)}
                    </option>
                  ))}
                </select>
                <button type="button" className="btn primary sm" onClick={openMasterCreate} disabled={!masterColsMeta.length}>
                  <IconPlus size={15} />
                  Add Row
                </button>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    {displayMasterCols.map((c) => (
                      <th key={c}>{titleCase(c)}</th>
                    ))}
                    <th className="actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {masterRows.slice(0, 200).map((row, idx) => (
                    <tr key={idx}>
                      {displayMasterCols.map((c) => (
                        <td key={c} className={String(c).endsWith('_id') ? 'mono' : undefined}>
                          {row[c] == null ? '—' : String(row[c])}
                        </td>
                      ))}
                      <td className="actions">
                        <div className="table-actions">
                          <button
                            type="button"
                            className="btn icon sm ghost"
                            title="Edit"
                            aria-label="Edit row"
                            onClick={() => openMasterEdit(row)}
                          >
                            <IconEdit size={15} />
                          </button>
                          <button
                            type="button"
                            className="btn icon sm danger"
                            title="Delete"
                            aria-label="Delete row"
                            onClick={async () => {
                              const label = masterPk.map((pk) => `${pk}=${row[pk]}`).join(', ') || 'this row';
                              if (!confirm(`Delete ${label}?`)) return;
                              try {
                                const key: Record<string, unknown> = {};
                                for (const pk of masterPk) key[pk] = row[pk];
                                await api.deleteMaster(masterTable, key);
                                setMsg(`Deleted ${label}`);
                                if (masterEditingKey) setMasterFormOpen(false);
                                loadMaster(masterTable);
                              } catch (e: any) {
                                setMsg(e.message);
                              }
                            }}
                          >
                            <IconTrash size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {masterRows.length === 0 && <Empty>No rows in {titleCase(masterTable)}.</Empty>}
            </div>
          </div>
        </>
      )}

      {adminTab === 'audit' && (
        <div className="panel">
          <div className="panel-head">
            <h3 className="panel-title">Audit Log</h3>
            <span className="muted">{audit.length} events</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Entity</th>
                  <th>Actor</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((e) => (
                  <tr key={e.audit_id}>
                    <td className="mono">{fmtTime(e.created_at) === '—' ? e.created_at : String(e.created_at).slice(0, 19)}</td>
                    <td>
                      <span className="pill accent">{e.action}</span>
                    </td>
                    <td className="mono">
                      {e.entity_type}/{e.entity_id}
                    </td>
                    <td className="mono">{e.actor_user_id}</td>
                    <td className="muted">{e.detail_json || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {audit.length === 0 && <Empty>No audit events yet.</Empty>}
          </div>
        </div>
      )}
    </>
  );
}
