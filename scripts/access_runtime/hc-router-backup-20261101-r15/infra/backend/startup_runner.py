"""One retrying bootstrap owner; dependency failures do not prevent HTTP liveness."""
import threading


class StartupRunner:
    def __init__(self, start, *, delay=5):
        self.start, self.delay = start, delay
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name='backend-bootstrap', daemon=True)

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.start()
                return
            except Exception as exc:
                print('[STARTUP] retry after ' + type(exc).__name__, flush=True)
                self.stop_event.wait(self.delay)

    def stop(self, timeout=2):
        self.stop_event.set()
        if self.thread.ident is not None:
            self.thread.join(timeout)
