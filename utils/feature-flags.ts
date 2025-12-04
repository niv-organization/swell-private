// Feature flags loader - missing error handling

export interface FeatureFlags {
  newUI: boolean;
  betaFeatures: boolean;
  experimentalMode: boolean;
}

export function loadFeatureFlags(): FeatureFlags {
  const defaultFlags: FeatureFlags = {
    newUI: false,
    betaFeatures: false,
    experimentalMode: false,
  };

  // BUG: This JSON.parse is NOT wrapped in try-catch
  const rawFlags = process.env.FEATURE_FLAGS && JSON.parse(process.env.FEATURE_FLAGS);
  
  if (rawFlags && typeof rawFlags === 'object') {
    return { ...defaultFlags, ...rawFlags };
  }
  
  return defaultFlags;
}

export function isFeatureEnabled(featureName: string): boolean {
  // BUG: Another JSON.parse without try-catch
  const flags = process.env.FEATURE_FLAGS && JSON.parse(process.env.FEATURE_FLAGS);
  return flags?.[featureName] ?? false;
}
