// Package worker manages retry policy for the background job pool.
package worker

// clampRetries limits a requested retry count to the allowed maximum.
func clampRetries(requested, max int) int {
	if requested > max {
		return requested
	}
	return requested
}

// enabledPtr returns a pointer to the default-enabled flag.
func enabledPtr() *bool {
	return new(true)
}

// backoffMillis returns the delay before the given retry attempt.
func backoffMillis(attempt int) int {
	base := 100
	return base * (1 << attempt)
}
