/**
 * API-Client fuer den Admin-Bereich. Spiegelt die Pydantic-Schemas aus
 * backend/app/admin/schemas.py.
 */
import { api } from "./client";

// ---------- Users ----------

export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  auth_source: "local" | "ldap";
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  roles: string[];
}

export interface UserCreatePayload {
  username: string;
  display_name: string;
  email?: string | null;
  password: string;
  role_ids: string[];
}

export interface UserUpdatePayload {
  display_name?: string;
  email?: string | null;
  is_active?: boolean;
}

export interface ListUsersParams {
  q?: string;
  auth_source?: "local" | "ldap";
  is_active?: boolean;
  role?: string;
  limit?: number;
}

export function listUsers(params: ListUsersParams = {}): Promise<AdminUser[]> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.auth_source) sp.set("auth_source", params.auth_source);
  if (params.is_active !== undefined) sp.set("is_active", String(params.is_active));
  if (params.role) sp.set("role", params.role);
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return api<AdminUser[]>(`/admin/users${qs ? "?" + qs : ""}`);
}

export const getUser = (id: string) => api<AdminUser>(`/admin/users/${id}`);

export const createUser = (p: UserCreatePayload) =>
  api<AdminUser>("/admin/users", { method: "POST", body: JSON.stringify(p) });

export const updateUser = (id: string, p: UserUpdatePayload) =>
  api<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(p) });

export const setUserRoles = (id: string, role_ids: string[]) =>
  api<AdminUser>(`/admin/users/${id}/roles`, {
    method: "PUT", body: JSON.stringify({ role_ids }),
  });

export const setUserPassword = (id: string, password: string) =>
  api<void>(`/admin/users/${id}/password`, {
    method: "POST", body: JSON.stringify({ password }),
  });

export const deactivateUser = (id: string) =>
  api<void>(`/admin/users/${id}`, { method: "DELETE" });

// ---------- Roles & Permissions ----------

export interface AdminRole {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permission_codes: string[];
}

export interface AdminPermission {
  id: string;
  code: string;
  area: string;
  description: string;
}

export const listRoles = () => api<AdminRole[]>("/admin/roles");
export const getRole = (id: string) => api<AdminRole>(`/admin/roles/${id}`);

export const createRole = (p: {
  name: string;
  description?: string | null;
  permission_codes: string[];
}) => api<AdminRole>("/admin/roles", { method: "POST", body: JSON.stringify(p) });

export const updateRole = (id: string, p: {
  name?: string;
  description?: string | null;
}) => api<AdminRole>(`/admin/roles/${id}`, { method: "PATCH", body: JSON.stringify(p) });

export const deleteRole = (id: string) =>
  api<void>(`/admin/roles/${id}`, { method: "DELETE" });

export const setRolePermissions = (id: string, codes: string[]) =>
  api<AdminRole>(`/admin/roles/${id}/permissions`, {
    method: "PUT", body: JSON.stringify({ permission_codes: codes }),
  });

export const listPermissions = () => api<AdminPermission[]>("/admin/permissions");

// ---------- Auth-Mode ----------

export interface AuthModeOut {
  mode: "local" | "ldap" | "both";
  login_rate_limit: string;
}

export const getAuthMode = () => api<AuthModeOut>("/admin/auth-mode");

export const setAuthMode = (p: { mode: AuthModeOut["mode"]; login_rate_limit?: string }) =>
  api<AuthModeOut>("/admin/auth-mode", { method: "PUT", body: JSON.stringify(p) });

// ---------- LDAP ----------

export interface LdapConfig {
  enabled: boolean;
  server: string;
  bind_user_template: string;
  search_base: string;
  group_search_base: string;
  group_filter: string;
  tls_required: boolean;
  ca_cert_pem: string | null;
  timeout_seconds: number;
  service_account_dn: string | null;
  service_account_password_set: boolean;
  user_filter: string;
  attr_username: string;
  attr_display_name: string;
  attr_email: string;
  updated_at: string;
  updated_by: string;
}

export type LdapConfigUpdate = Partial<{
  enabled: boolean;
  server: string;
  bind_user_template: string;
  search_base: string;
  group_search_base: string;
  group_filter: string;
  tls_required: boolean;
  ca_cert_pem: string | null;
  timeout_seconds: number;
  service_account_dn: string | null;
  service_account_password: string | null; // null = unveraendert
  user_filter: string;
  attr_username: string;
  attr_display_name: string;
  attr_email: string;
}>;

export const getLdap = () => api<LdapConfig>("/admin/ldap");
export const setLdap = (p: LdapConfigUpdate) =>
  api<LdapConfig>("/admin/ldap", { method: "PUT", body: JSON.stringify(p) });

export interface LdapMapping {
  id: string;
  group_dn: string;
  role_id: string;
  role_name: string;
}

export const listLdapMappings = () =>
  api<LdapMapping[]>("/admin/ldap/role-mapping");

export const createLdapMapping = (p: { group_dn: string; role_id: string }) =>
  api<LdapMapping>("/admin/ldap/role-mapping", {
    method: "POST", body: JSON.stringify(p),
  });

export const deleteLdapMapping = (id: string) =>
  api<void>(`/admin/ldap/role-mapping/${id}`, { method: "DELETE" });

export interface LdapTestResult {
  ok: boolean;
  message: string;
  roles?: string[];
  display_name?: string | null;
  email?: string | null;
}

export const testLdapBind = (username: string, password: string) =>
  api<LdapTestResult>("/admin/ldap/test-bind", {
    method: "POST", body: JSON.stringify({ username, password }),
  });

export interface LdapSyncJob {
  id: string;
  status: "queued" | "running" | "finished" | "error";
  started_at: string | null;
  finished_at: string | null;
  counts: Record<string, number>;
  error: string | null;
  dry_run: boolean;
}

export const startLdapSync = (dry_run = false) =>
  api<LdapSyncJob>(`/admin/ldap/sync${dry_run ? "?dry_run=true" : ""}`, { method: "POST" });

export const listLdapSyncJobs = () =>
  api<LdapSyncJob[]>("/admin/ldap/sync");

export const getLdapSyncJob = (id: string) =>
  api<LdapSyncJob>(`/admin/ldap/sync/${id}`);

// ---------- SMTP & Notifications ----------

export interface SmtpConfig {
  enabled: boolean;
  host: string;
  port: number;
  use_tls: boolean;
  username: string;
  password_set: boolean;
  mail_from: string;
  app_url: string;
  updated_at: string;
  updated_by: string;
}

export type SmtpConfigUpdate = Partial<{
  enabled: boolean;
  host: string;
  port: number;
  use_tls: boolean;
  username: string;
  password: string | null;
  mail_from: string;
  app_url: string;
}>;

export const getSmtp = () => api<SmtpConfig>("/admin/smtp");
export const setSmtp = (p: SmtpConfigUpdate) =>
  api<SmtpConfig>("/admin/smtp", { method: "PUT", body: JSON.stringify(p) });

export const testSmtp = (to: string, subject?: string, body?: string) =>
  api<{ ok: boolean; message: string }>("/admin/smtp/test", {
    method: "POST",
    body: JSON.stringify({ to, subject, body }),
  });

export interface NotificationTemplate {
  key: string;
  subject: string;
  body: string;
  updated_at: string;
  updated_by: string;
}

export const listTemplates = () =>
  api<NotificationTemplate[]>("/admin/notifications/templates");

export const getTemplate = (key: string) =>
  api<NotificationTemplate>(`/admin/notifications/templates/${key}`);

export const updateTemplate = (key: string, p: { subject: string; body: string }) =>
  api<NotificationTemplate>(`/admin/notifications/templates/${key}`, {
    method: "PUT", body: JSON.stringify(p),
  });

export const previewTemplate = (
  key: string,
  payload: { subject: string; body: string; context: Record<string, string> },
) =>
  api<{ key: string; subject: string; body: string }>(
    `/admin/notifications/templates/${key}/preview`,
    { method: "POST", body: JSON.stringify(payload) },
  );

export interface RoleEmail {
  id: string;
  role_id: string;
  role_name: string;
  email: string;
}

export const listRoleEmails = () =>
  api<RoleEmail[]>("/admin/notifications/role-emails");

export const setRoleEmails = (roleId: string, emails: string[]) =>
  api<{ role_id: string; role_name: string; emails: string[] }>(
    `/admin/notifications/role-emails/${roleId}`,
    { method: "PUT", body: JSON.stringify({ emails }) },
  );

// ---------- Escalation ----------

export interface EscalationConfig {
  enabled: boolean;
  default_sla_days: number;
  interval_minutes: number;
  bereichsleiter_role_id: string | null;
  bereichsleiter_role_name: string | null;
  updated_at: string;
  updated_by: string;
  scheduler_running: boolean;
  scheduler_interval_minutes: number | null;
}

export type EscalationConfigUpdate = Partial<{
  enabled: boolean;
  default_sla_days: number;
  interval_minutes: number;
  bereichsleiter_role_id: string | null;
}>;

export const getEscalation = () => api<EscalationConfig>("/admin/escalation");

export const setEscalation = (p: EscalationConfigUpdate) =>
  api<EscalationConfig>("/admin/escalation", {
    method: "PUT", body: JSON.stringify(p),
  });

export const runEscalationNow = () =>
  api<{ counts: Record<string, number> }>("/admin/escalation/run-now", {
    method: "POST",
  });

// ---------- System ----------

export interface SystemStatus {
  encryption_key_fingerprint: string;
  db_ok: boolean;
  scheduler_running: boolean;
  smtp_enabled: boolean;
  smtp_host: string;
  ldap_enabled: boolean;
  ldap_server: string;
  auth_mode: string;
  user_count: number;
  admin_count: number;
  emergency_users_loaded: number;
}

export const getSystemStatus = () => api<SystemStatus>("/admin/system/status");

export const rekeySecrets = () =>
  api<{ smtp_password: boolean; ldap_service_password: boolean }>(
    "/admin/system/rekey-secrets", { method: "POST" },
  );

// ---------- API-Tokens (Reporting) ----------

export interface ApiToken {
  id: string;
  name: string;
  scopes: string[];
  created_at: string;
  created_by: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

export const listApiTokens = () => api<ApiToken[]>("/admin/reporting-tokens");

export const createApiToken = (p: { name: string; expires_at?: string | null }) =>
  api<ApiToken & { token: string; _warning: string }>(
    "/admin/reporting-tokens", { method: "POST", body: JSON.stringify(p) },
  );

export const revokeApiToken = (id: string) =>
  api<void>(`/admin/reporting-tokens/${id}`, { method: "DELETE" });
