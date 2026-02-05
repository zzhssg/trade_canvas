import { useState } from "react";
import { createWorktree } from "../../lib/devApi";

interface CreateWorktreeModalProps {
  onClose: () => void;
  onCreated: () => void;
}

export function CreateWorktreeModal({
  onClose,
  onCreated,
}: CreateWorktreeModalProps) {
  const [branch, setBranch] = useState("");
  const [description, setDescription] = useState("");
  const [planPath, setPlanPath] = useState("");
  const [baseBranch, setBaseBranch] = useState("main");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (description.length < 20) {
      setError("Description must be at least 20 characters");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await createWorktree({
        branch,
        description,
        plan_path: planPath || null,
        base_branch: baseBranch,
      });

      if (res.ok) {
        onCreated();
      } else {
        setError(res.error || "Failed to create worktree");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create worktree");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg rounded-lg border border-white/10 bg-zinc-900 p-6">
        <h2 className="text-lg font-semibold">Create New Worktree</h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Branch name */}
          <div>
            <label className="block text-sm font-medium text-white/80">
              Branch Name
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="feature/my-feature"
              required
              className="mt-1 w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-white/80">
              Description (min 20 chars)
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what this worktree is for..."
              required
              rows={3}
              className="mt-1 w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            <div className="mt-1 text-xs text-white/50">
              {description.length}/20 characters
            </div>
          </div>

          {/* Plan path */}
          <div>
            <label className="block text-sm font-medium text-white/80">
              Plan Path (optional)
            </label>
            <input
              type="text"
              value={planPath}
              onChange={(e) => setPlanPath(e.target.value)}
              placeholder="docs/plan/2026-02-xx-feature.md"
              className="mt-1 w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>

          {/* Base branch */}
          <div>
            <label className="block text-sm font-medium text-white/80">
              Base Branch
            </label>
            <input
              type="text"
              value={baseBranch}
              onChange={(e) => setBaseBranch(e.target.value)}
              className="mt-1 w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-md bg-red-900/50 px-3 py-2 text-sm text-red-200">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-white/20 px-4 py-2 text-sm font-medium hover:bg-white/10"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !branch || description.length < 20}
              className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-50"
            >
              {loading ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
