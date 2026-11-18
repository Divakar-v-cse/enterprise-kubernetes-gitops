import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { DEFAULT_CONFIG, setRuntimeConfig } from "./api";
import type { RuntimeConfig } from "./api";

const STORAGE_KEY = "gitops-platform.settings.v1";

export const SETTINGS_STORAGE_KEY = STORAGE_KEY;

function readStoredConfig(): RuntimeConfig {
  if (typeof window === "undefined") return { ...DEFAULT_CONFIG };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_CONFIG };
    const parsed = JSON.parse(raw) as Partial<RuntimeConfig>;
    return {
      apiBase: typeof parsed.apiBase === "string" && parsed.apiBase ? parsed.apiBase : DEFAULT_CONFIG.apiBase,
      gatewayBase:
        typeof parsed.gatewayBase === "string" && parsed.gatewayBase
          ? parsed.gatewayBase
          : DEFAULT_CONFIG.gatewayBase,
      token: typeof parsed.token === "string" ? parsed.token : DEFAULT_CONFIG.token,
      apiKey:
        typeof parsed.apiKey === "string" && parsed.apiKey ? parsed.apiKey : DEFAULT_CONFIG.apiKey,
    };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

// Configure the API client before the first render so early requests use the
// persisted base URL and token.
setRuntimeConfig(readStoredConfig());

export interface SettingsContextValue {
  config: RuntimeConfig;
  save: (next: RuntimeConfig) => void;
  reset: () => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<RuntimeConfig>(() => readStoredConfig());

  useEffect(() => {
    setRuntimeConfig(config);
  }, [config]);

  const save = useCallback((next: RuntimeConfig) => {
    const normalised: RuntimeConfig = {
      apiBase: next.apiBase.trim() || DEFAULT_CONFIG.apiBase,
      gatewayBase: next.gatewayBase.trim() || DEFAULT_CONFIG.gatewayBase,
      token: next.token.trim(),
      apiKey: next.apiKey.trim() || DEFAULT_CONFIG.apiKey,
    };
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalised));
    } catch {
      // Private-mode storage failures must not break the dashboard.
    }
    setRuntimeConfig(normalised);
    setConfig(normalised);
  }, []);

  const reset = useCallback(() => {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    setRuntimeConfig(DEFAULT_CONFIG);
    setConfig({ ...DEFAULT_CONFIG });
  }, []);

  const value = useMemo<SettingsContextValue>(() => ({ config, save, reset }), [config, save, reset]);

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used inside SettingsProvider");
  }
  return context;
}
