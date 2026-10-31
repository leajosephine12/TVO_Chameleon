import type { Category, Priority, ReviewStatus, WcagCheck } from '../domain/review';

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const CATEGORY_LABEL: Record<Category, string> = {
  cognitive: 'Cognitive',
  wcag: 'WCAG',
  reading: 'Reading',
};

export const PRIORITY_LABEL: Record<Priority, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export const STATUS_LABEL: Record<ReviewStatus, string> = {
  open: 'Open',
  approved: 'Approved',
  rejected: 'Rejected',
};

export const WCAG_CHECK_LABEL: Record<WcagCheck, string> = {
  pass: 'WCAG check: pass',
  fail: 'WCAG check: fail',
  review: 'WCAG check: needs review',
};
