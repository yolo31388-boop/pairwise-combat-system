"""Pytest hooks for the combat test-suite.

The test classes in ``tests/`` are plain classes (they do not inherit
from ``unittest.TestCase``) but call ``self.assertIsNotNone``. Provide
the assertion methods they rely on without modifying the test files.
"""


def _assert_is_not_none(self, value, msg=None):
    if value is None:
        raise AssertionError(msg or "expected a non-None value, got None")


def _assert_is_none(self, value, msg=None):
    if value is not None:
        raise AssertionError(msg or f"expected None, got {value!r}")


def _assert_true(self, value, msg=None):
    if not value:
        raise AssertionError(msg or f"expected a truthy value, got {value!r}")


def _assert_false(self, value, msg=None):
    if value:
        raise AssertionError(msg or f"expected a falsy value, got {value!r}")


def _assert_equal(self, first, second, msg=None):
    if first != second:
        raise AssertionError(msg or f"{first!r} != {second!r}")


_INJECTED_ASSERTIONS = {
    "assertIsNotNone": _assert_is_not_none,
    "assertIsNone": _assert_is_none,
    "assertTrue": _assert_true,
    "assertFalse": _assert_false,
    "assertEqual": _assert_equal,
}


def pytest_collection_modifyitems(items):
    for item in items:
        cls = getattr(item, "cls", None)
        if cls is None:
            continue
        for name, func in _INJECTED_ASSERTIONS.items():
            if not hasattr(cls, name):
                setattr(cls, name, func)
