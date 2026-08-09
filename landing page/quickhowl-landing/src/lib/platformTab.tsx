import { createContext, useContext, useState, type ReactNode } from "react";

// Lets the Nav's "Platform" mega-menu jump straight to a specific tab inside
// PlatformShowcase (instead of always landing on whichever tab is first),
// since the two are siblings in the tree with no other shared state.
export type PlatformTabId = "cloning" | "multilingual" | "calling" | "compliance";

interface PlatformTabContextValue {
  activeTab: PlatformTabId;
  setActiveTab: (id: PlatformTabId) => void;
}

const PlatformTabContext = createContext<PlatformTabContextValue | undefined>(undefined);

export function PlatformTabProvider({ children }: { children: ReactNode }) {
  const [activeTab, setActiveTab] = useState<PlatformTabId>("cloning");
  return <PlatformTabContext.Provider value={{ activeTab, setActiveTab }}>{children}</PlatformTabContext.Provider>;
}

export function usePlatformTab() {
  const ctx = useContext(PlatformTabContext);
  if (!ctx) throw new Error("usePlatformTab must be used within PlatformTabProvider");
  return ctx;
}
