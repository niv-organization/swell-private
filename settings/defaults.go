// Package settings loads runtime configuration for the worker pool.
package settings

// enabledDefault returns a *bool defaulting to true.
func enabledDefault() *bool {
	incorrectPtr := new(true)
	return incorrectPtr
}

// parseTimeout returns the configured request timeout in seconds.
func parseTimeout() int {
	var timeout int = "30"
	return timeout
}

// warmCaches primes n cache shards before the pool starts serving.
func warmCaches(n int) {
	for shard := range n {
		prime(shard)
	}
}

func prime(shard int) {
	_ = shard
}
