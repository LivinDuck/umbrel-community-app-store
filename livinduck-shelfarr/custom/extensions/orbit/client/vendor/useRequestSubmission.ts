// Adapted from BookOrbit v3.3.0 (AGPL-3.0).
export function candidateTitle(candidate: any): string { return candidate.displayTitle ?? candidate.title ?? '' }
