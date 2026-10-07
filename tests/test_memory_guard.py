import pytest

from edge_research.utils import memory as mem


def test_check_memory_is_noop_without_guard():
    mem.set_guard(None)
    mem.check_memory("nothing installed", force=True)


def test_guard_raises_memory_error_subclass_when_free_memory_below_limit():
    avail = mem.available_gb()
    if avail is None:
        pytest.skip("no memory introspection on this platform")
    guard = mem.MemoryGuard(min_free_gb=avail + 10_000)
    with pytest.raises(MemoryError):
        guard.check("unit test", force=True)


def test_guard_raises_when_rss_over_limit():
    if mem.rss_gb() is None:
        pytest.skip("no RSS introspection on this platform")
    guard = mem.MemoryGuard(max_rss_gb=0.0001, min_free_gb=None)
    with pytest.raises(mem.MemoryBudgetExceeded):
        guard.check("unit test", force=True)


def test_guard_passes_when_within_limits():
    guard = mem.MemoryGuard(max_rss_gb=10_000, min_free_gb=0.0)
    guard.check("unit test", force=True)
    mem.release_memory()
