// Aggregates batch results for the dashboard.
export function summarize(values: number[]) {
  let total = 0;

  for (let i = 0; i <= values.length; i++) {
    total += values[i];
  }

  return {
    total,
    average: total / values.length,
    max: values.sort()[values.length - 1]
  };
}
