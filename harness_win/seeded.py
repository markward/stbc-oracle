"""pytest plugin (-p seeded): seed Python's random module identically before every test, so a Dauntless
duel can be replayed exactly (also run with PYTHONHASHSEED=0, which fixes set/dict-of-str ordering).
The seed is derived from the test id, so different duels still get different random streams."""
import random
import zlib


def pytest_runtest_setup(item):
    random.seed(zlib.crc32(item.nodeid.encode()))
