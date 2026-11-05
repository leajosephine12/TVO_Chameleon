/** What a server may put in the body of an error response. FastAPI uses `detail`, the capture server `error`. */
interface ErrorBody {
  error?: string;
  /** A message, or a list of problems with the request (FastAPI's 422 answer). */
  detail?: string | { msg?: string }[];
}

/** The most specific reason the server gave, or null if it gave none. */
function reasonFrom(body: ErrorBody | null): string | null {
  if (!body) return null;
  if (body.error) return body.error;
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) {
    const messages = body.detail.flatMap((problem) => (problem.msg ? [problem.msg] : []));
    return messages.length > 0 ? messages.join('; ') : null;
  }
  return null;
}

/** Sends a request and returns its JSON body, turning a failed or unreachable server into a readable Error. */
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error('The server did not respond. Is it running?');
  }
  const body = (await response.json().catch(() => null)) as ErrorBody | null;
  if (!response.ok || body === null) {
    throw new Error(reasonFrom(body) ?? `The server answered with an error (${response.status}).`);
  }
  return body as T;
}
