/** Sends a request and returns its JSON body, turning a failed or unreachable server into a readable Error. */
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error('The server did not respond. Is it running?');
  }
  const body = (await response.json().catch(() => null)) as { error?: string } | null;
  if (!response.ok || body === null) {
    throw new Error(body?.error ?? `The server answered with an error (${response.status}).`);
  }
  return body as T;
}
