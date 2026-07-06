from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    ERROR = 1
    ISSUES = 2
    USAGE = 64
    TIMEOUT = 124
    MISSING_BINARY = 127
    INTERRUPT = 130
