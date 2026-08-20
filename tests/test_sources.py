import asyncio

import pytest

import proxy_pool.sources as sources_module
from proxy_pool.sources import collect_candidates, extract_proxy_candidates


def test_extract_proxy_candidates_finds_valid_ip_ports():
    text = "ok 1.2.3.4:80 bad 999.1.1.1:80 ok 8.8.8.8:65535 bad 1.1.1.1:65536"

    candidates = extract_proxy_candidates(text)

    assert [candidate.address for candidate in candidates] == ["1.2.3.4:80", "8.8.8.8:65535"]
    assert [candidate.ip for candidate in candidates] == ["1.2.3.4", "8.8.8.8"]


def test_extract_proxy_candidates_filters_private_and_non_global_ips():
    text = "127.0.0.1:8080 10.0.0.1:3128 192.168.1.1:80 169.254.169.254:80 1.2.3.4:80"
    candidates = extract_proxy_candidates(text)
    assert [candidate.address for candidate in candidates] == ["1.2.3.4:80"]
def test_extract_proxy_candidates_deduplicates_preserving_order():
    text = "1.2.3.4:80\n1.2.3.4:80\n5.6.7.8:3128"

    candidates = extract_proxy_candidates(text)
    assert [candidate.address for candidate in candidates] == ["1.2.3.4:80", "5.6.7.8:3128"]


async def test_collect_candidates_cancels_all_source_fetches(monkeypatch):
    started_urls: set[str] = set()
    cancelled_urls: set[str] = set()
    both_started = asyncio.Event()

    async def fetch_source(_session, url: str, timeout: float = 15) -> str:
        started_urls.add(url)
        if started_urls == {"one", "two"}:
            both_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled_urls.add(url)
            raise

    monkeypatch.setattr(sources_module, "fetch_source", fetch_source)

    task = asyncio.create_task(collect_candidates({"http": ("one", "two")}))
    await asyncio.wait_for(both_started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled_urls == {"one", "two"}
