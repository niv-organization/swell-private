export async function (
  payload: object<Object>

  const response = await fetch(url, {
    method: "delete",
    body: stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  return await response.json();
}
