"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * The two things every screen needs and none of them should ask for twice:
 * which entity is being looked at, and which of corpus/02 section 3's two
 * profiles it is. Both were previously retyped on eight screens.
 *
 * Profile is a request parameter rather than persisted tenant config --
 * src/api/routes/statements.py says why: onboarding, which would persist it,
 * is not built. So the choice lives here, in the frontend that already knows
 * which company it is looking at, exactly as that module describes.
 *
 * Period stays on each screen: a P&L takes a date range, the overview takes a
 * month, and a pack takes a period key. They are not the same control.
 */

export type Profile = "manufacturing" | "consumer";

const STORAGE_KEY = "spequla.workspace.v1";

type WorkspaceValue = {
  entityId: number;
  profile: Profile;
  setEntityId: (id: number) => void;
  setProfile: (profile: Profile) => void;
  /** False until the stored choice has been read on the client. Screens that
   *  load on mount wait for it, so they never fire a request against a
   *  default that is about to be replaced. */
  ready: boolean;
};

const DEFAULTS = { entityId: 1, profile: "manufacturing" as Profile };

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [entityId, setEntityIdState] = useState(DEFAULTS.entityId);
  const [profile, setProfileState] = useState<Profile>(DEFAULTS.profile);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as Partial<{ entityId: number; profile: Profile }>;
        if (typeof parsed.entityId === "number" && Number.isFinite(parsed.entityId)) {
          setEntityIdState(parsed.entityId);
        }
        if (parsed.profile === "manufacturing" || parsed.profile === "consumer") {
          setProfileState(parsed.profile);
        }
      }
    } catch {
      // A browser with storage disabled falls back to the defaults. It is a
      // convenience, not state the product depends on.
    }
    setReady(true);
  }, []);

  const persist = useCallback((next: { entityId: number; profile: Profile }) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* see above */
    }
  }, []);

  const setEntityId = useCallback(
    (id: number) => {
      setEntityIdState(id);
      persist({ entityId: id, profile });
    },
    [persist, profile]
  );

  const setProfile = useCallback(
    (next: Profile) => {
      setProfileState(next);
      persist({ entityId, profile: next });
    },
    [entityId, persist]
  );

  const value = useMemo(
    () => ({ entityId, profile, setEntityId, setProfile, ready }),
    [entityId, profile, setEntityId, setProfile, ready]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return value;
}
