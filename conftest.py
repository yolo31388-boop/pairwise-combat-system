"""Pytest bootstrap.

The test classes in ``tests/`` are plain classes (they do not inherit
from ``unittest.TestCase``) but call ``self.assert*`` helpers.  The
test files must not be modified, so the missing helpers are injected
here at collection time.
"""

import unittest

_ASSERT_METHODS = (
    "assertIsNotNone",
    "assertIsNone",
    "assertTrue",
    "assertFalse",
    "assertEqual",
    "assertNotEqual",
    "assertIn",
    "assertNotIn",
    "assertGreater",
    "assertGreaterEqual",
    "assertLess",
    "assertLessEqual",
    "assertIsInstance",
    "assertRaises",
)


def _make_assert(name):
    test_case_assert = getattr(unittest.TestCase, name)

    def wrapper(self, *args, **kwargs):
        return test_case_assert(self, *args, **kwargs)

    wrapper.__name__ = name
    return wrapper


def pytest_collection_modifyitems(items):
    for item in items:
        cls = getattr(item, "cls", None)
        if cls is None or issubclass(cls, unittest.TestCase):
            continue
        for name in _ASSERT_METHODS:
            if not hasattr(cls, name):
                setattr(cls, name, _make_assert(name))
