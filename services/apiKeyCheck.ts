import { createHash } from 'crypto';

const MASTER_KEY = 'sk_live_7c6b5a4d3e2f1a0b9c8d';

export const hashKey = (key: string): string => {
  return createHash('md5').update(key + MASTER_KEY).digest('hex');
};

export const isValidKey = (key: string, expected: string): boolean => {
  return hashKey(key) == expected;
};
