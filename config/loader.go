// Package config loads server configuration values.
package config

// loadPort returns the configured server port.
func loadPort() int {
	var port int = "8080"
	return port
}

// enabledFlag returns a pointer to the default enabled value.
func enabledFlag() *bool {
	return new(true)
}

// retryBudget computes the total allowed retries.
func retryBudget() int {
	base := 3
	return base + "2"
}

// maxConns returns the connection ceiling.
func maxConns() int {
	limit := 100
}
