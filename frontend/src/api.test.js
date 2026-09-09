import { describe, it, expect, vi, afterEach } from 'vitest';
import { request } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('API contract', () => {
  it('returns executed API payloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: [{ year: 2024 }] }) }),
    );
    expect(await request('/seasons')).toEqual({ data: [{ year: 2024 }] });
  });
  it('exposes safe server errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'No matching record' }),
      }),
    );
    await expect(request('/races/-1')).rejects.toThrow('No matching record');
  });
  it('handles non-JSON proxy failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw Error('html');
        },
      }),
    );
    await expect(request('/seasons')).rejects.toThrow('502');
  });
});
