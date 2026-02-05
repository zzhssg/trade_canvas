import type { WorktreeInfo } from "../../lib/devApi";
import { deleteWorktree } from "../../lib/devApi";
import { useState } from "react";

interface WorktreeCardProps {
  worktree: WorktreeInfo;
  onStart: () => void;
  onStop: () => void;
  onOpen: () => void;
  onRefresh: () => void;
}

export function WorktreeCard({
  worktree,
  onStart,
  onStop,
  onOpen,
  onRefresh,
}: WorktreeCardProps) {
  const [deleting, setDeleting] = useState(false);

  const backendRunning = worktree.services?.backend?.running ?? false;
  const frontendRunning = worktree.services?.frontend?.running ?? false;
  const anyRunning = backendRunning || frontendRunning;

  const handleDelete = async () => {
    if (!confirm(`Delete worktree "${worktree.branch}"? This cannot be undone.`)) {
      return;
    }
    setDeleting(true);
    try {
      const res = await deleteWorktree(worktree.id, true);
      if (res.ok) {
        onRefresh();
      } else {
        alert(res.error || "Failed to delete worktree");
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to delete worktree");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-medium">
              {worktree.is_main ? "main" : worktree.branch}
            </h3>
            {worktree.is_main && (
              <span className="rounded bg-sky-600/30 px-2 py-0.5 text-xs text-sky-300">
                Main
              </span>
            )}
            {worktree.is_detached && (
              <span className="rounded bg-amber-600/30 px-2 py-0.5 text-xs text-amber-300">
                Detached
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-white/60">
            <span className="font-mono">{worktree.commit}</span>
            <span className="mx-2">|</span>
            <span className="truncate">{worktree.path}</span>
          </div>
        </div>
      </div>

      {/* Description */}
      {worktree.metadata?.description && (
        <div className="mt-3 text-sm text-white/80">
          {worktree.metadata.description}
        </div>
      )}

      {/* Plan link */}
      {worktree.metadata?.plan_path && (
        <div className="mt-2 text-sm">
          <span className="text-white/50">Plan: </span>
          <span className="text-sky-400">{worktree.metadata.plan_path}</span>
        </div>
      )}

      {/* Services status */}
      <div className="mt-4 flex items-center gap-4">
        <ServiceBadge
          label="Backend"
          port={worktree.services?.backend?.port ?? 0}
          running={backendRunning}
        />
        <ServiceBadge
          label="Frontend"
          port={worktree.services?.frontend?.port ?? 0}
          running={frontendRunning}
        />
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2">
        {anyRunning ? (
          <>
            <button
              type="button"
              onClick={onStop}
              className="rounded-md bg-red-600/80 px-3 py-1.5 text-sm font-medium hover:bg-red-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            >
              Stop
            </button>
            <button
              type="button"
              onClick={onOpen}
              className="rounded-md bg-sky-600/80 px-3 py-1.5 text-sm font-medium hover:bg-sky-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            >
              Open
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={onStart}
            className="rounded-md bg-emerald-600/80 px-3 py-1.5 text-sm font-medium hover:bg-emerald-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          >
            Start
          </button>
        )}

        {!worktree.is_main && (
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting || anyRunning}
            className="rounded-md border border-red-500/50 px-3 py-1.5 text-sm font-medium text-red-400 hover:bg-red-500/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50"
          >
            {deleting ? "Deleting..." : "Delete"}
          </button>
        )}
      </div>
    </div>
  );
}

function ServiceBadge({
  label,
  port,
  running,
}: {
  label: string;
  port: number;
  running: boolean;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span
        className={`h-2 w-2 rounded-full ${
          running ? "bg-emerald-500" : "bg-white/30"
        }`}
      />
      <span className="text-white/70">{label}:</span>
      <span className="font-mono text-white/90">{port || "-"}</span>
    </div>
  );
}
