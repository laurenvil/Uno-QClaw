package protocoltypes

import "errors"

// ErrStreamingUnsupported is returned by a Streamable provider's ChatStream
// when the requested configuration cannot be streamed — for example, when
// tools are passed to a backend whose streaming path is text-only. Callers
// should treat this as a signal to fall back to the buffered Chat() path
// silently rather than surface it as an error to the user.
var ErrStreamingUnsupported = errors.New("streaming not supported for this configuration")
