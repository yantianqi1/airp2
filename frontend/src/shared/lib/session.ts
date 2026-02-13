export function createSessionId(): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `rp-${Date.now().toString(36)}-${rand}`;
}

export function normalizeCharacterName(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

export function normalizeCharacterList(list: string[]): string[] {
  const deduped = new Set<string>();
  for (const item of list) {
    const normalized = normalizeCharacterName(item);
    if (normalized) {
      deduped.add(normalized);
    }
  }
  return Array.from(deduped);
}
