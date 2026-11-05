import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestJson } from './requestJson';

/** Makes the next request answer with the given status and JSON body. */
function answerWith(status: number, body: unknown): void {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe('requestJson', () => {
  it('returns the body of a successful answer', async () => {
    answerWith(200, { ok: true });

    await expect(requestJson('/x')).resolves.toEqual({ ok: true });
  });

  it('shows the capture server error message', async () => {
    answerWith(400, { error: 'That host is not allowed.' });

    await expect(requestJson('/x')).rejects.toThrow('That host is not allowed.');
  });

  it("shows FastAPI's detail message", async () => {
    answerWith(500, { detail: 'Model is not configured.' });

    await expect(requestJson('/x')).rejects.toThrow('Model is not configured.');
  });

  it("shows FastAPI's list of problems with the request", async () => {
    answerWith(422, { detail: [{ msg: 'Field required' }, { msg: 'Input should be a string' }] });

    await expect(requestJson('/x')).rejects.toThrow('Field required; Input should be a string');
  });

  it('falls back to the status when the server gives no reason', async () => {
    answerWith(500, {});

    await expect(requestJson('/x')).rejects.toThrow('The server answered with an error (500).');
  });
});
