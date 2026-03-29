// Auto-generated SDK stub.
export const SDK_TITLE = 'Arctis';
export async function getHealth(baseUrl: string, apiKey: string) {
  const res = await fetch(`${baseUrl}/health`, { headers: { 'X-API-Key': apiKey } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
