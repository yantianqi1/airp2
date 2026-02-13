export type AuthMode = 'user' | 'guest';

export interface AuthUser {
  id: string;
  username: string;
}

export interface MeResponse {
  mode: AuthMode;
  user?: AuthUser;
  guest_id?: string;
}

