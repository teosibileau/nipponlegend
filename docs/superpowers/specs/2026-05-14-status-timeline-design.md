# Per-item status timeline

Date: 2026-05-14
Author: Teo (via grill-me)
Status: Ready for implementation plan

## Problem

Hunt items in `src/content/hunts/*.mdx` have a `status` of `missing`, `confirmed`, or `purchased`. Today that status is a single field with no record of when or why it changed. As Teo begins working with sellers to confirm specific SKUs, three things become important:

1. **When** each transition happened.
2. **Which candidate** was confirmed or purchased at that moment (since seller-confirmed picks can change — out-of-stock swaps, returns, brand substitutions).
3. **Why** it changed, in seller-facing language ("vendedor confirmó por WhatsApp", "no había stock — misma pieza otra marca").

The hunt MDX is hand-edited, the matcher (`scripts/hunt.py`) is hands-off for human decisions, and rendering must show the audit trail per part. Status is no longer a state — it's a derived view of a history of events.

## Decisions

Each decision below was settled through an explicit grill. The justification is preserved so future readers can see *why* a choice was made.

### 1. Model: append-only event log per item

Each item carries a `history[]` array of status-transition events, in chronological order. Status is **derived** from the tail of this array. Reversions (e.g., `confirmed → missing` when a seller backs out) are recorded as new events, never as edits or deletions of past events.

Rejected: per-status timestamps (`confirmedAt`, `purchasedAt`) — loses reversions and notes. Rejected: single `statusChangedAt` — loses everything but the most recent change.

### 2. Event shape: status + full pick snapshot + optional note

Each event carries enough information to render the timeline row and the "currently chosen" winner card without joining to any other data:

```ts
{
  status: 'missing' | 'confirmed' | 'purchased';
  at: Date;                        // YYYY-MM-DD, date-only
  pick?: {                         // omitted on 'missing' reversion events
    site: string;
    url: string;                   // canonical candidate URL
    sku?: string | null;
    title: string;
    score?: number;                // optional snapshot of matcher score at confirmation time
    notes?: string[];              // optional snapshot of matcher notes
  };
  note?: string;                   // freshly-typed seller-facing context
}
```

The pick is a **full snapshot**, not a back-reference. This is deliberate: the matcher mutates `alternates[]` on every run, so a back-reference can become stale or fall off the list entirely. A self-contained pick survives any future catalog change.

Rejected: thin pick that looks up title/score from `alternates[]` — fragile against matcher mutation. Rejected: status-only events with no pick — loses the *thing being confirmed*, which is the entire point of the seller-in-the-loop workflow.

### 3. Source of truth: derive status (and chosen) from history

The schema **removes** the `status` and `chosen` fields from the item shape. Both are derived at render time:

```ts
const lastEvent = item.history.at(-1);
const status = lastEvent?.status ?? 'missing';        // empty history ⇒ missing
const winner = lastEvent?.pick ?? (alternates[0] ?? null);
const isPicked = !!lastEvent?.pick;
```

Rejected: store both `status` and `history`, with or without a Zod refinement to enforce agreement — hand-editing two fields per transition is a drift trap. The same logic applies to `chosen`, even though dropping it means events carry larger pick snapshots.

### 4. The "missing" baseline: empty history means missing

Items are born with `history: []` (Zod default). No synthetic "added on hunt.date" event is seeded. `missing` is the **absence of seller-side events**, which matches the domain meaning of the status. The hunt's own `date` field provides the implicit "born on" timestamp.

Rejected: born with a `{status: missing, at: hunt.date}` seed event — inflates the log with N redundant timestamps equal to `hunt.date`. Rejected: render synthesizes a leading row from `hunt.date` — pure UI concern, can be added later without a schema change.

### 5. Date granularity: date-only, order by array position

`at` is a YAML date literal (`2026-05-14`). Same-day multi-event ordering comes from array position — first written is first happened. No timezones, no time components, no separate sequence number.

Rejected: ISO datetime — invites timezone bugs (typing `2026-05-14T13:32` without offset parses as UTC, shifts the displayed day). Rejected: `seq?: number` — escape hatch for a problem that doesn't exist yet. Easy to add later.

### 6. Matcher: history-blind, zero code changes

`scripts/hunt.py` continues to do exactly what it does today: refresh `alternates[]` and `lastRun` for every item. It never reads or writes `history[]`. Round-trip preservation is already guaranteed by `yaml.safe_dump(..., sort_keys=False)`.

Re-scoring already-purchased items continues — the matcher's responsibility is catalog freshness, not status awareness. Coupling them would mean updating the matcher every time the status model changes.

Rejected: freeze `alternates` for `purchased` items — couples matcher to status semantics, creates stale-data footgun on reverts. Rejected: freeze `confirmed + purchased` — same issue, larger blast radius.

### 7. UI: inline always-visible timeline per item

When `history.length > 0`, render an `<ol class="timeline">` block inside `PartItem.astro`, after the alternates `<details>` dropdown and before the part's closing tag. Each row:

```
<date>   <status pip word>   <sku or url-host>   <note>
```

- Date in monospace.
- Status word styled with the existing pip color tokens.
- SKU rendered as a link to `pick.url`. If `sku` is null/absent, link text is the URL's hostname-and-path tail.
- `missing` reversion events have no pick — render date + status + note only.
- Note in muted text, italic.

Rejected: collapsed `<details>` — contradicts "represent transitions" by hiding them behind a click. Rejected: status pip becomes a row of historical pips — loses notes and pick details, which are the most useful parts of the audit trail.

No hunt-level activity feed in this iteration. The hunt index already exposes `última corrida`; a separate cross-item activity stream is YAGNI until more than one hunt is active.

### 8. Migration of `2026-05-revision-tren-delantero.mdx`

The existing hunt has 13 items, all at `status: missing` with `chosen: null` and no seller events. Migration is a one-pass edit:

1. Remove every `  status: missing` line (13 occurrences).
2. Remove every `  chosen: null` line (13 occurrences).
3. Do **not** add `history: []` — Zod's `.default([])` handles the absence.

Net diff: -26 lines, +0 lines. Rendered output is identical (status derives to `missing`, no pick, alternates unchanged).

Rejected: leave `status:` and `chosen:` lines in place and let Zod silently strip unknown keys — leaves dead fields in the YAML that confuse future readers. Rejected: deprecate-and-ignore approach — accumulates schema cruft permanently.

### 9. Hunt-page counters

The status-counting loop in `src/pages/hunts/[slug].astro` updates from:

```ts
for (const it of hunt.data.items) counts[it.status as keyof typeof counts]++;
```

to:

```ts
for (const it of hunt.data.items) {
  const status = it.history.at(-1)?.status ?? 'missing';
  counts[status]++;
}
```

Single-line behavior change. The pip-counter UI at the top of the hunt page continues to show accurate `falta / confirmado / comprado` totals.

## Concrete schema diff

`src/content.config.ts`:

```diff
+const pickSchema = z.object({
+  site: z.string(),
+  url: z.string().url(),
+  sku: z.string().nullable().optional(),
+  title: z.string(),
+  score: z.number().optional(),
+  notes: z.array(z.string()).default([]),
+});
+
+const eventSchema = z.object({
+  status: z.enum(['missing', 'confirmed', 'purchased']),
+  at: z.date(),
+  pick: pickSchema.optional(),
+  note: z.string().optional(),
+});
+
 const hunts = defineCollection({
   loader: glob({ pattern: '**/*.mdx', base: './src/content/hunts' }),
   schema: z.object({
     name: z.string(),
     vehicle: z.string(),
     date: z.date(),
     lastRun: z.date().optional().nullable(),
     items: z.array(
       z.object({
         id: z.string(),
         name: z.string(),
         qty: z.number().int().default(1),
-        status: z.enum(['missing', 'confirmed', 'purchased']).default('missing'),
         desc: z.string(),
         searchTerms: z.array(z.string()).default([]),
-        chosen: candidateSchema.nullable().default(null),
         alternates: z.array(candidateSchema).default([]),
+        history: z.array(eventSchema).default([]),
       })
     ),
   }),
 });
```

## Authoring example

When the seller confirms a part by WhatsApp, append one entry to the item's `history`. Most fields come from copy-pasting an entry out of the existing `alternates[]` block — only `at` and `note` are freshly typed:

```yaml
history:
- status: confirmed
  at: 2026-06-03
  pick:
    site: nipponpartsweb
    url: https://nipponpartsweb.com.ar/product/rotula-inferior-toyota-hilux-4x4-1994-al-2004/
    sku: IM14210/TAKAMA/TRC/GRZ-8706-completa
    title: Rotula Inferior Toyota Hilux 4×4 1994 Al 2004
  note: vendedor confirmó por WhatsApp
```

A later out-of-stock swap is one more entry:

```yaml
- status: confirmed
  at: 2026-06-10
  pick:
    site: nipponpartsweb
    url: https://nipponpartsweb.com.ar/product/.../
    sku: IM-30501
    title: Fuelle Homocinetica Toyota Hilux 1997-2004 4x4 Lado Rueda
  note: no había stock; vendedor ofreció IM-30501 misma pieza otra marca
```

A reversion (seller backs out, returned part) is an entry with no `pick`:

```yaml
- status: missing
  at: 2026-06-15
  note: devuelto, vendedor confió en marca incorrecta
```

## Files touched

- `src/content.config.ts` — schema changes per the diff above.
- `src/components/PartItem.astro` — derive `status`/`winner`/`isPicked` from history; render the inline timeline.
- `src/components/StatusPip.astro` — no change (still receives a status string, just from a derived source).
- `src/pages/hunts/[slug].astro` — counter loop change.
- `src/content/hunts/2026-05-revision-tren-delantero.mdx` — strip `status:` and `chosen:` lines.
- `scripts/hunt.py` — **no change** (yaml round-trip preserves history).
- Styles for `.timeline` — added inline in `PartItem.astro`'s scoped styles, alongside the existing `.candidate` rules.

## Out of scope (deferred)

- Hunt-level activity feed across all items.
- Price tracking (`priceArs?` on `purchased` events).
- Synthetic "added on hunt.date" leading row in the rendered timeline.
- Same-day event ordering via explicit `seq:` field.

Each is a non-breaking addition if it becomes necessary later — no schema migration needed for any of them.
