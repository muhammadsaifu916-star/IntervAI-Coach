export const EXPERIENCE_TIER_DISPLAY: Record<string, string> = {
  'Entry Level': '0-3 years (Entry Level)',
  'Mid Level': '4-6 years (Mid Level)',
  'Senior Level': '7+ years (Senior Level)',
};

export function getExperienceDisplay(
  years?: number | null,
  tier?: string | null
): string {
  const value = Number(years);

  if (value === 1) return EXPERIENCE_TIER_DISPLAY['Entry Level'];
  if (value === 3) return EXPERIENCE_TIER_DISPLAY['Mid Level'];
  if (value === 5) return EXPERIENCE_TIER_DISPLAY['Senior Level'];

  if (tier && EXPERIENCE_TIER_DISPLAY[tier]) {
    return EXPERIENCE_TIER_DISPLAY[tier];
  }

  return '—';
}