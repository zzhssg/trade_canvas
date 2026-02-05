/**
 * Dev Panel API client for worktree management.
 */

const API_BASE = "";

export interface ServiceState {
  running: boolean;
  port: number;
  pid: number | null;
  url: string | null;
}

export interface ServiceStatus {
  backend: ServiceState;
  frontend: ServiceState;
}

export interface WorktreeMetadata {
  description: string;
  plan_path: string | null;
  created_at: string;
  owner: string | null;
  ports: Record<string, number>;
}

export interface WorktreeInfo {
  id: string;
  path: string;
  branch: string;
  commit: string;
  is_detached: boolean;
  is_main: boolean;
  metadata: WorktreeMetadata | null;
  services: ServiceStatus | null;
}

export interface WorktreeListResponse {
  worktrees: WorktreeInfo[];
}

export interface CreateWorktreeRequest {
  branch: string;
  description: string;
  plan_path?: string | null;
  base_branch?: string;
}

export interface CreateWorktreeResponse {
  ok: boolean;
  worktree: WorktreeInfo | null;
  error: string | null;
}

export interface StartServicesRequest {
  backend_port?: number | null;
  frontend_port?: number | null;
}

export interface StartServicesResponse {
  ok: boolean;
  services: ServiceStatus | null;
  error: string | null;
}

export interface StopServicesResponse {
  ok: boolean;
  error: string | null;
}

export interface DeleteWorktreeResponse {
  ok: boolean;
  error: string | null;
}

export interface PortAllocationResponse {
  backend_port: number;
  frontend_port: number;
}

export async function listWorktrees(): Promise<WorktreeListResponse> {
  const res = await fetch(`${API_BASE}/api/dev/worktrees`);
  if (!res.ok) throw new Error(`Failed to list worktrees: ${res.status}`);
  return res.json();
}

export async function getWorktree(worktreeId: string): Promise<WorktreeInfo> {
  const res = await fetch(`${API_BASE}/api/dev/worktrees/${worktreeId}`);
  if (!res.ok) throw new Error(`Failed to get worktree: ${res.status}`);
  return res.json();
}

export async function createWorktree(
  req: CreateWorktreeRequest
): Promise<CreateWorktreeResponse> {
  const res = await fetch(`${API_BASE}/api/dev/worktrees`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Failed to create worktree: ${res.status}`);
  return res.json();
}

export async function startServices(
  worktreeId: string,
  req: StartServicesRequest = {}
): Promise<StartServicesResponse> {
  const res = await fetch(`${API_BASE}/api/dev/worktrees/${worktreeId}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Failed to start services: ${res.status}`);
  return res.json();
}

export async function stopServices(
  worktreeId: string
): Promise<StopServicesResponse> {
  const res = await fetch(`${API_BASE}/api/dev/worktrees/${worktreeId}/stop`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to stop services: ${res.status}`);
  return res.json();
}

export async function deleteWorktree(
  worktreeId: string,
  force = false
): Promise<DeleteWorktreeResponse> {
  const res = await fetch(`${API_BASE}/api/dev/worktrees/${worktreeId}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  if (!res.ok) throw new Error(`Failed to delete worktree: ${res.status}`);
  return res.json();
}

export async function allocatePorts(): Promise<PortAllocationResponse> {
  const res = await fetch(`${API_BASE}/api/dev/ports/allocate`);
  if (!res.ok) throw new Error(`Failed to allocate ports: ${res.status}`);
  return res.json();
}
