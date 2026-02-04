import { createContext, useContext } from "react";

type CenterScrollLockApi = {
  lock: () => void;
  unlock: () => void;
};

const CenterScrollLockContext = createContext<CenterScrollLockApi | null>(null);

export function CenterScrollLockProvider({
  value,
  children
}: {
  value: CenterScrollLockApi;
  children: React.ReactNode;
}) {
  return <CenterScrollLockContext.Provider value={value}>{children}</CenterScrollLockContext.Provider>;
}

export function useCenterScrollLock() {
  return useContext(CenterScrollLockContext);
}

