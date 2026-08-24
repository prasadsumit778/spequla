"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ui/States";

/**
 * The last line of defence: a finance user never sees a raw stack trace or a
 * white page. Whatever failed, nothing in their data changed -- say so.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-2xl py-12">
      <ErrorState
        title="This screen could not be shown"
        message={error.message || "An unexpected error occurred while rendering this screen."}
        hint="No data was changed. If it happens again, note the reference below and send it to your SPEQULA analyst."
        onRetry={reset}
        retryLabel="Reload this screen"
      />
      {error.digest && (
        <p className="mt-3 text-[12px] text-ink-faint">
          Reference: <span className="font-mono">{error.digest}</span>
        </p>
      )}
    </div>
  );
}
