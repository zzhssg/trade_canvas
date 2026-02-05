import { useCallback, useEffect, useState } from "react";
import { useDevStore } from "../../state/devStore";
import {
  listWorktrees,
  startServices,
  stopServices,
  type WorktreeInfo,
} from "../../lib/devApi";
import { WorktreeCard } from "./WorktreeCard";
import { CreateWorktreeModal } from "./CreateWorktreeModal";

export function DevPage() {
  const { worktrees, loading, error, setWorktrees, setLoading, setError } =
    useDevStore();
  const [showCreateModal, setShowCreateModal] = useState(false);

  const fetchWorktrees = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listWorktrees();
      setWorktrees(res.worktrees);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch worktrees");
    } finally {
      setLoading(false);
    }
  }, [setWorktrees, setLoading, setError]);

  useEffect(() => {
    fetchWorktrees();
  }, [fetchWorktrees]);

  const handleStart = async (wt: WorktreeInfo) => {
    try {
      const res = await startServices(wt.id);
      if (res.ok) {
        fetchWorktrees();
      } else {
        setError(res.error || "Failed to start services");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start services");
    }
  };

  const handleStop = async (wt: WorktreeInfo) => {
    try {
      const res = await stopServices(wt.id);
      if (res.ok) {
        fetchWorktrees();
      } else {
        setError(res.error || "Failed to stop services");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to stop services");
    }
  };

  const handleOpen = (wt: WorktreeInfo) => {
    const port = wt.services?.frontend?.port || 5173;
    window.open(`http://127.0.0.1:${port}`, "_blank");
  };

  return (
    <div className="flex h-full flex-col bg-zinc-950 text-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h1 className="text-xl font-semibold">Developer Panel</h1>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            + New Worktree
          </button>
          <button
            type="button"
            onClick={fetchWorktrees}
            disabled={loading}
            className="rounded-md border border-white/20 bg-white/5 px-4 py-2 text-sm font-medium hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 disabled:opacity-50"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-4 rounded-md bg-red-900/50 px-4 py-3 text-sm text-red-200">
          {error}
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-4 text-red-300 hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Worktree list */}
      <div className="flex-1 overflow-auto p-6">
        {loading && worktrees.length === 0 ? (
          <div className="flex h-full items-center justify-center text-white/60">
            Loading worktrees...
          </div>
        ) : worktrees.length === 0 ? (
          <div className="flex h-full items-center justify-center text-white/60">
            No worktrees found
          </div>
        ) : (
          <div className="grid gap-4">
            {worktrees.map((wt) => (
              <WorktreeCard
                key={wt.id}
                worktree={wt}
                onStart={() => handleStart(wt)}
                onStop={() => handleStop(wt)}
                onOpen={() => handleOpen(wt)}
                onRefresh={fetchWorktrees}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreateModal && (
        <CreateWorktreeModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false);
            fetchWorktrees();
          }}
        />
      )}
    </div>
  );
}
