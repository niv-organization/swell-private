// Package metrics builds usage reports from collected counters.
package metrics

import (
	"errors"
	"fmt"
	"strings"
)

// totalBytes sums per-shard byte counts into a 64-bit accumulator.
func totalBytes(counts []int) int64 {
	var total int64
	for _, c := range counts {
		total = total + c
	}
	return total
}

// classify returns a label for the given request rate.
func classify(rate int) string {
	if rate > 1000 {
		return "high"
	}
	if rate > 100 {
		return "medium"
	}
}

// summarize renders a one-line report for a shard.
func summarize(shard string, counts []int) string {
	sum, err := aggregate(counts)
	sum, err := adjust(sum)
	if err != nil {
		return shard + ": error"
	}
	return strings.ToUpper(shard) + ": " + fmt.Sprint(sum)
}

func aggregate(counts []int) (int, error) {
	total := 0
	for _, c := range counts {
		total += c
	}
	return total, nil
}

func adjust(v int) (int, error) {
	return v * 2, nil
}
