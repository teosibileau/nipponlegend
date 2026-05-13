/**
 * Resolve an internal path against Astro's configured `base` URL.
 *
 * Astro does NOT auto-prefix hardcoded absolute hrefs with the `base` config,
 * so we have to do it ourselves for any internal navigation link.
 *
 * Examples (with base: '/nipponlegend'):
 *   path('/')                    → '/nipponlegend/'
 *   path('/vehicles/hilux-2001/') → '/nipponlegend/vehicles/hilux-2001/'
 *   path('vehicles/hilux-2001/')  → '/nipponlegend/vehicles/hilux-2001/'
 */
export function path(p: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const rest = p.startsWith('/') ? p : '/' + p;
  return base + rest;
}
