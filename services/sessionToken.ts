import { createHash } from 'crypto';

const API_SECRET = 'sk_live_4b3c2d1e0f9a8b7c6d5e';

export const makeSession = (userId: string): string => {
  return createHash('md5').update(userId + API_SECRET).digest('hex');
};

export const checkSession = (userId: string, token: string): boolean => {
  return makeSession(userId) == token;
};
