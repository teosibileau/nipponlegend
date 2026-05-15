import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const candidateSchema = z.object({
  site: z.string(),
  url: z.string().url(),
  title: z.string(),
  sku: z.string().nullable().optional(),
  score: z.number(),
  notes: z.array(z.string()).default([]),
});

const pickSchema = z.object({
  site: z.string(),
  url: z.string().url(),
  sku: z.string().nullable().optional(),
  title: z.string(),
  score: z.number().optional(),
  notes: z.array(z.string()).default([]),
});

const eventSchema = z.object({
  status: z.enum(['missing', 'confirmed', 'purchased']),
  at: z.date(),
  pick: pickSchema.optional(),
  note: z.string().optional(),
});

const sites = defineCollection({
  loader: glob({ pattern: '**/*.mdx', base: './src/content/sites' }),
  schema: z.object({
    name: z.string(),
    baseUrl: z.string().url(),
    adapter: z.string(),
    config: z.record(z.any()).default({}),
  }),
});

const vehicles = defineCollection({
  loader: glob({ pattern: '**/*.mdx', base: './src/content/vehicles' }),
  schema: z.object({
    name: z.string(),
    vin: z.string().optional(),
    make: z.string(),
    model: z.string(),
    year: z.number().int(),
    yearRange: z.tuple([z.number().int(), z.number().int()]),
    chassis: z.string().optional(),
    engineCode: z.string().optional(),
    displacement: z.string().optional(),
    drive: z.string().optional(),
    body: z.string().optional(),
    plant: z.string().optional(),
    qualifiers: z.array(z.string()).default([]),
    disqualifiers: z.array(z.string()).default([]),
    huntOn: z.array(z.string()).default([]),
    sources: z
      .array(
        z.object({
          url: z.string().url(),
          title: z.string(),
          claim: z.string().optional(),
        })
      )
      .default([]),
  }),
});

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
        desc: z.string(),
        searchTerms: z.array(z.string()).default([]),
        alternates: z.array(candidateSchema).default([]),
        history: z.array(eventSchema).default([]),
      })
    ),
  }),
});

export const collections = { sites, vehicles, hunts };
