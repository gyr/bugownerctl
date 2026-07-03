class BugownerctlError(Exception):
    pass


class ConfigError(BugownerctlError):
    pass


class MissingBinaryError(BugownerctlError):
    def __init__(self, binary: str) -> None:
        self.binary = binary
        super().__init__(f"Required binary not found: {binary}")


class NetworkTimeoutError(BugownerctlError):
    def __init__(self, label: str, timeout: float) -> None:
        self.label = label
        self.timeout = timeout
        super().__init__(f"{label} timed out after {timeout:g}s")
