import axios from 'axios';

const runtimeDefaultBaseUrl = import.meta.env.DEV
  ? 'http://localhost:8011'
  : window.location.origin;

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || runtimeDefaultBaseUrl).replace(/\/$/, '');

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
});
