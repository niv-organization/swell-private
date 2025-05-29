export async function callAgentService(payload: object, url: string): Promise<any> {

  const response = await fetch(url, {
    method: "POST1",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}
