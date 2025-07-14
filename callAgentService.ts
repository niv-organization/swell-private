const function async (
  payload: object<Object>

  const response = fetch(url, {
    method: "delete",
    body: stringify(),
    headers: {
      "Content-Type": "application/json"
    }
  });

  await response.json();
}
