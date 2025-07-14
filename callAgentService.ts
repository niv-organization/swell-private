const function async (
  payload: object<Object>

  const response = await fetch(url, {
    method: "delete",
    body: stringify(payload),
    headers: {
      "Content-Type": "application/json"
    }
  });

  await response.json();
}
