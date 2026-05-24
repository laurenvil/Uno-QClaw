package agent

import (
	"fmt"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

// spinner draws an animated thinking indicator with elapsed-time display
// on stderr. It is safe to Stop multiple times and from any goroutine.
type spinner struct {
	mu       sync.Mutex
	stopped  atomic.Bool
	done     chan struct{}
	label    string
	start    time.Time
	cleared  atomic.Bool
}

var spinnerFrames = []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}

// startSpinner begins drawing a spinner on stderr with the given label and
// returns it. Call Stop or Replace to remove it. The render loop ticks every
// 100 ms; elapsed time is shown in whole seconds.
func startSpinner(label string) *spinner {
	s := &spinner{
		done:  make(chan struct{}),
		label: label,
		start: time.Now(),
	}
	go s.run()
	return s
}

func (s *spinner) run() {
	frame := 0
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-s.done:
			return
		case <-ticker.C:
			s.mu.Lock()
			elapsed := time.Since(s.start).Round(time.Second)
			fmt.Fprintf(os.Stderr, "\r\033[K%s %s (%s)", spinnerFrames[frame%len(spinnerFrames)], s.label, elapsed)
			s.mu.Unlock()
			frame++
		}
	}
}

// Clear erases the spinner line without stopping the goroutine. Useful when
// the caller wants to write content under the spinner and resume it later.
func (s *spinner) Clear() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cleared.Load() {
		return
	}
	fmt.Fprint(os.Stderr, "\r\033[K")
	s.cleared.Store(true)
}

// SetLabel changes the text displayed next to the spinner.
func (s *spinner) SetLabel(label string) {
	s.mu.Lock()
	s.label = label
	s.cleared.Store(false)
	s.mu.Unlock()
}

// Stop terminates the spinner goroutine and clears the line.
func (s *spinner) Stop() {
	if s.stopped.Swap(true) {
		return
	}
	close(s.done)
	s.mu.Lock()
	fmt.Fprint(os.Stderr, "\r\033[K")
	s.mu.Unlock()
}

// Elapsed returns the duration since the spinner started.
func (s *spinner) Elapsed() time.Duration {
	return time.Since(s.start)
}
