"use client";

import { useEffect } from "react";
import Button from "./Button";

/**
 * The confirmation step in front of an action a person cannot undo from the
 * screen they are on. It states what will happen in plain words and requires
 * a second, deliberate click -- and it focuses the safe control, not the
 * destructive one, so a stray Enter cannot fire it.
 *
 * Deliberately one small component built from the existing Button primitive
 * and the same card tokens as Card.tsx, rather than a dialog library
 * (CLAUDE.md section 6: do not build a design system).
 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  busy = false,
  busyLabel,
  error,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  busyLabel?: string;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // Escape cancels. An in-flight action is not cancellable mid-request, so
  // Escape is ignored while busy rather than closing the dialog over a write
  // that is still running.
  useEffect(() => {
    if (!open || busy) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-full max-w-md rounded-card border border-line bg-surface shadow-raised"
      >
        <div className="border-b border-line px-5 py-3.5">
          <h2 id="confirm-dialog-title" className="text-[15px] leading-6 font-semibold">
            {title}
          </h2>
        </div>
        <div className="px-5 py-4">
          {description && <div className="text-[13px] leading-5 text-ink-muted">{description}</div>}
          {error && <p className="mt-3 text-[12.5px] text-neg">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-line bg-surface-muted px-5 py-3">
          {/* autoFocus, not a ref: Button is a plain function component and
              this project is on React 18, where ref is not a normal prop. */}
          <Button autoFocus variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm} busy={busy} busyLabel={busyLabel}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
