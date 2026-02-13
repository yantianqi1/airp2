import { z } from 'zod';
import { apiClient } from './client';
import type { MeResponse } from '../types/auth';

const authUserSchema = z.object({
  id: z.string(),
  username: z.string(),
});

const meSchema = z.object({
  mode: z.union([z.literal('user'), z.literal('guest')]),
  user: authUserSchema.optional(),
  guest_id: z.string().optional(),
});

const authOkSchema = z.object({
  mode: z.union([z.literal('user'), z.literal('guest')]).optional(),
  user: authUserSchema.optional(),
  guest_id: z.string().optional(),
  ok: z.boolean().optional(),
});

export async function getMe(): Promise<MeResponse> {
  const response = await apiClient.get('/api/v1/auth/me');
  return meSchema.parse(response.data);
}

export async function ensureGuest(): Promise<MeResponse> {
  const response = await apiClient.post('/api/v1/auth/guest', {});
  return meSchema.parse(response.data);
}

export async function login(username: string, password: string): Promise<MeResponse> {
  const response = await apiClient.post('/api/v1/auth/login', { username, password });
  return meSchema.parse(response.data);
}

export async function register(username: string, password: string): Promise<MeResponse> {
  const response = await apiClient.post('/api/v1/auth/register', { username, password });
  return meSchema.parse(response.data);
}

export async function logout(): Promise<void> {
  const response = await apiClient.post('/api/v1/auth/logout', {});
  authOkSchema.parse(response.data);
}

