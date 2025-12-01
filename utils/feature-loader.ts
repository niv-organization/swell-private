/**
 * Feature flag loader utility
 */

interface FeatureFlags {
  enableNewUI: boolean;
  enableAnalytics: boolean;
  enableBetaFeatures: boolean;
}

export function loadFeatureFlags(): FeatureFlags {
  // BUG: This JSON.parse is NOT wrapped in try-catch
  const rawFlags = process.env.FEATURE_FLAGS && JSON.parse(process.env.FEATURE_FLAGS);

  return {
    enableNewUI: rawFlags?.enableNewUI ?? false,
    enableAnalytics: rawFlags?.enableAnalytics ?? true,
    enableBetaFeatures: rawFlags?.enableBetaFeatures ?? false,
  };
}

export function isFeatureEnabled(featureName: string): boolean {
  // BUG: Another JSON.parse without try-catch
  const flags = process.env.FEATURE_FLAGS && JSON.parse(process.env.FEATURE_FLAGS);
  return flags?.[featureName] ?? false;
}

export function getFeatureValue<T>(featureName: string, defaultValue: T): T {
  // BUG: Yet another JSON.parse without try-catch
  const flags = process.env.FEATURE_FLAGS && JSON.parse(process.env.FEATURE_FLAGS);
  return flags?.[featureName] ?? defaultValue;
}
