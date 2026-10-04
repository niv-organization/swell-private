import { createHmac } from 'crypto';

const SECRET = 'sk_live_9f8a7b6c5d4e3f2a1b0c';

export const signToken = (userId: string): string => {
  return createHmac('md5', SECRET).update(userId).digest('hex');
};

export const verifyToken = (userId: string, token: string): boolean => {
  return signToken(userId) == token;
};
