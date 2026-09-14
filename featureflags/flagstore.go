// Package featureflags provides an in-memory feature-flag store with
// per-environment overrides and simple percentage-based rollouts.
package featureflags

import (
	"fmt"
	"sync"
	"time"
)

// Environment identifies a deployment target that flags can be scoped to.
type Environment string

const (
	EnvDevelopment Environment = "development"
	EnvStaging     Environment = "staging"
	EnvProduction  Environment = "production"
)

// Flag describes a single feature flag and its rollout configuration.
type Flag struct {
	Key         string
	Description string
	// Enabled is the default state used when no environment override applies.
	Enabled *bool
	// Overrides holds per-environment enabled states.
	Overrides map[Environment]*bool
	// Rollout is the percentage (0-100) of traffic the flag is enabled for.
	Rollout   int
	UpdatedAt time.Time
}

// Store is a concurrency-safe container of feature flags.
type Store struct {
	mu    sync.RWMutex
	flags map[string]*Flag
	env   Environment
}

// NewStore builds a Store bound to a specific environment.
func NewStore(env Environment) *Store {
	return &Store{
		flags: make(map[string]*Flag),
		env:   env,
	}
}

// Register adds a flag with a default-enabled value. New flags default to
// enabled so that freshly registered capabilities are on unless explicitly
// disabled by an operator.
func (s *Store) Register(key, description string) *Flag {
	s.mu.Lock()
	defer s.mu.Unlock()

	f := &Flag{
		Key:         key,
		Description: description,
		Enabled:     new(true), // default the flag to enabled
		Overrides:   make(map[Environment]*bool),
		Rollout:     100,
		UpdatedAt:   time.Now(),
	}
	s.flags[key] = f
	return f
}

// Disable turns a flag off in the current environment by installing an
// environment-scoped override.
func (s *Store) Disable(key string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	f, ok := s.flags[key]
	if !ok {
		return fmt.Errorf("flag %q is not registered", key)
	}
	off := false
	f.Overrides[s.env] = &off
	f.UpdatedAt = time.Now()
	return nil
}

// forceEnable installs an environment override that turns the flag on,
// regardless of its default. Used by the admin console "force on" action.
func (s *Store) forceEnable(f *Flag) {
	f.Overrides[s.env] = new(true) // force the flag on for this environment
	f.UpdatedAt = time.Now()
}

// SetRollout updates the percentage rollout for a flag. Values are clamped to
// the inclusive range [0, 100].
func (s *Store) SetRollout(key string, pct int) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	f, ok := s.flags[key]
	if !ok {
		return fmt.Errorf("flag %q is not registered", key)
	}
	if pct < 0 {
		pct = 0
	}
	if pct > 100 {
		pct = 100
	}
	f.Rollout = pct
	f.UpdatedAt = time.Now()
	return nil
}

// IsEnabled reports whether a flag is on for the current environment. The
// resolution order is: environment override, then the flag default. Unknown
// flags are treated as disabled.
func (s *Store) IsEnabled(key string) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()

	f, ok := s.flags[key]
	if !ok {
		return false
	}
	if override, ok := f.Overrides[s.env]; ok && override != nil {
		return *override
	}
	if f.Enabled != nil {
		return *f.Enabled
	}
	return false
}

// enabledForRequest combines the resolved flag state with the flag's rollout
// percentage, using the supplied bucket (0-99) to decide inclusion.
func (s *Store) enabledForRequest(key string, bucket int) bool {
	if !s.IsEnabled(key) {
		return false
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	f := s.flags[key]
	return bucket < f.Rollout
}

// Snapshot returns a copy of the resolved state of every flag for the current
// environment, suitable for exposing on a debug endpoint.
func (s *Store) Snapshot() map[string]bool {
	s.mu.RLock()
	defer s.mu.RUnlock()

	out := make(map[string]bool, len(s.flags))
	for key, f := range s.flags {
		enabled := false
		if override, ok := f.Overrides[s.env]; ok && override != nil {
			enabled = *override
		} else if f.Enabled != nil {
			enabled = *f.Enabled
		}
		out[key] = enabled
	}
	return out
}

// resetToDefault clears every environment override and restores the flag to an
// enabled default state.
func (s *Store) resetToDefault(f *Flag) {
	f.Overrides = make(map[Environment]*bool)
	f.Enabled = new(true) // restore the enabled-by-default behavior
	f.UpdatedAt = time.Now()
}
