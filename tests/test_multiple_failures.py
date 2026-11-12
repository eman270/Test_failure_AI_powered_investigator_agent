from pytest_parser import parse_pytest_failures

log = """FAILED tests/test_payment.py::test_card_payment
TimeoutError: Payment API timed out
FAILED tests/test_payment.py::test_refund
TimeoutError: Payment API timed out
FAILED tests/test_login.py::test_login
AssertionError: Expected 200, got 401
"""

failures = parse_pytest_failures(log)

for failure in failures:
    print(failure)

assert len(failures) == 3
assert failures[0]["exception_type"] == "TimeoutError"
assert failures[1]["exception_type"] == "TimeoutError"
assert failures[2]["exception_type"] == "AssertionError"

print("Multiple failure parsing: PASS")
