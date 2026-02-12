"""EscapeWatcher - detect bare Escape key press during streaming queries"""

import os
import select
import sys
import threading

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None


class EscapeWatcher:
    """Watch for bare Escape key press in a background thread.

    Distinguishes bare Escape (cancel) from escape sequences like arrow keys
    by waiting briefly after receiving \\x1b for follow-up bytes.

    Usage:
        cancel_event = threading.Event()
        with EscapeWatcher(cancel_event):
            # ... streaming loop ...
            if cancel_event.is_set():
                break
    """

    ESCAPE_TIMEOUT = 0.05  # 50ms to distinguish bare Escape from sequences

    def __init__(self, cancel_event: threading.Event):
        self._cancel_event = cancel_event
        self._thread: threading.Thread | None = None
        self._stop_read_fd: int | None = None
        self._stop_write_fd: int | None = None
        self._stdin_fd: int | None = None
        self._original_attrs = None

    def start(self):
        if not sys.stdin.isatty():
            return

        if termios is None:
            return

        self._stdin_fd = sys.stdin.fileno()
        self._original_attrs = termios.tcgetattr(self._stdin_fd)

        self._stop_read_fd, self._stop_write_fd = os.pipe()

        tty.setcbreak(self._stdin_fd)

        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        if self._thread is None:
            return

        # Signal thread to stop
        if self._stop_write_fd is not None:
            try:
                os.write(self._stop_write_fd, b"x")
            except OSError:
                pass

        self._thread.join(timeout=1.0)

        # Restore terminal
        if self._original_attrs is not None and self._stdin_fd is not None:
            try:
                termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._original_attrs)
            except (termios.error, OSError):
                pass

        # Close pipe fds
        for fd in (self._stop_read_fd, self._stop_write_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._stop_read_fd = None
        self._stop_write_fd = None

    def _watch_loop(self):
        stdin_fd = self._stdin_fd
        stop_fd = self._stop_read_fd

        while True:
            try:
                readable, _, _ = select.select([stdin_fd, stop_fd], [], [])
            except (ValueError, OSError):
                break

            if stop_fd in readable:
                break

            if stdin_fd in readable:
                try:
                    ch = os.read(stdin_fd, 1)
                except OSError:
                    break

                if ch == b"\x1b":
                    # Wait briefly for follow-up bytes (escape sequence)
                    ready, _, _ = select.select([stdin_fd, stop_fd], [], [], self.ESCAPE_TIMEOUT)

                    if stop_fd in ready:
                        break

                    if stdin_fd in ready:
                        # Follow-up bytes arrived — this is an escape sequence, consume and ignore
                        try:
                            os.read(stdin_fd, 16)
                        except OSError:
                            pass
                    else:
                        # No follow-up — bare Escape
                        self._cancel_event.set()
                        break

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
