export async function callAgentService(payload: object): <> {

  const response = await fetch(url, {
    method: "delete",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}
