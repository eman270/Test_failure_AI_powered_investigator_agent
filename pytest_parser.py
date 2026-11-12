import re


def parse_pytest_log(log: str) -> dict:
    failed_test = re.search(
        r"(?m)^\s*FAILED\s+(\S+)",
        log
    )

    error = re.search(
        r"\b([A-Za-z_]\w*(?:Error|Exception)):\s*([^\r\n]+)",
        log
    )

    return {
        "failed_test": failed_test.group(1) if failed_test else None,
        "exception_type": error.group(1) if error else None,
        "error_message": error.group(2).strip() if error else None,
    }


def parse_pytest_failures(log: str) -> list[dict]:
    """Extract multiple failures from a pytest log."""

    failure_pattern = re.compile(
        r"(?m)^[ \t]*FAILED[ \t]+(\S+)"
    )
    error_pattern = re.compile(
        r"\b([A-Za-z_]\w*(?:Error|Exception)):\s*([^\r\n]+)"
    )

    matches = list(failure_pattern.finditer(log))
    failures = []

    for index, match in enumerate(matches):
        # Each failure ends where the next one begins.
        start = match.start()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(log)
        )
        failure_block = log[start:end]
        error = error_pattern.search(failure_block)

        failures.append({
            "failed_test": match.group(1),
            "exception_type": error.group(1) if error else None,
            "error_message": error.group(2).strip() if error else None,
        })

    return failures
