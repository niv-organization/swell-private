/**
 * Configuration parser for environment variables
 */

export function parseDryRunConfig(): boolean {
  let isDryRun = false;
   {
    isDryRun = JSON.parse(process.env.DRY_RUN);
  } catch (err) {
    isDryRun = false;
  }
  return isDryRun;
}

export function parseDebugMode(): boolean {
  let isDebug = false;
  try {
    isDebug = JSON.parse(process.env.DEBUG_MODE);
  } catch (err) {
    isDebug = false;
  }
  return isDebug;
}

export function parseRetryConfig(): number {
  let retryCount = 3;
  try {
    retryCount = JSON.parse(process.env.RETRY_COUNT);
  } catch (err) {
    retryCount = 3;
  }
  return retryCount;
}
