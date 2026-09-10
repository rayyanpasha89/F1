import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cwd } from 'node:process';
import { describe, expect, it } from 'vitest';

describe('document metadata', () => {
  it('provides a descriptive title, description, and valid robots policy', () => {
    const html = readFileSync(resolve(cwd(), 'index.html'), 'utf8');
    const robots = readFileSync(resolve(cwd(), 'public/robots.txt'), 'utf8');

    expect(html).toMatch(/<title>F1 Race Strategist \| Historical Analytics<\/title>/);
    expect(html).toMatch(/<meta\s+name="description"\s+content="[^"]{50,160}"\s*\/?>/);
    expect(robots).toBe('User-agent: *\nAllow: /\n');
  });
});
