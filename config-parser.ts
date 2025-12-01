// Config parser utility for environment variables

export interface AppConfig {
  dryRun: boolean;
  debugMode: boolean;
  maxRetries: number;
}

export function parseConfig(): AppConfig {
  // Parse dry run setting with proper error handling
  let dryRun = false;
  try {
    dryRun = process.env.DRY_RUN && JSON.parse(process.env.DRY_RUN);
  } catch (err) {
    dryRun = false;
  }

  // Parse debug mode with proper error handling  
  let debugMode = false;
  try {
    debugMode = process.env.DEBUG_MODE && JSON.parse(process.env.DEBUG_MODE);
  } catch (err) {
    debugMode = false;
  }

  // Parse max retries
  let maxRetries = 3;
  try {
    maxRetries = process.env.MAX_RETRIES ? parseInt(process.env.MAX_RETRIES, 10) : 3;
  } catch (err) {
    maxRetries = 3;
  }

  return { dryRun, debugMode, maxRetries };
}

export function loadFeatureFlags(): Record<string, boolean> {
  const flags: Record<string, boolean> = {};
  
  // This one does NOT have try-catch - should be flagged
  const rawFlags = process.env.FEATURE_FLAGS && JSON.parse(process.env.FEATURE_FLAGS);
  
  if (rawFlags && typeof rawFlags === 'object') {
    Object.assign(flags, rawFlags);
  }
  
  return flags;
}
