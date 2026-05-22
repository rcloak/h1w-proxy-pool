from proxy_pool.sources import extract_proxy_candidates


def test_extract_proxy_candidates_finds_valid_ip_ports():
    text = "ok 1.2.3.4:80 bad 999.1.1.1:80 ok 10.0.0.1:65535 bad 1.1.1.1:65536"

    candidates = extract_proxy_candidates(text)

    assert [candidate.address for candidate in candidates] == ["1.2.3.4:80", "10.0.0.1:65535"]
    assert [candidate.ip for candidate in candidates] == ["1.2.3.4", "10.0.0.1"]


def test_extract_proxy_candidates_deduplicates_preserving_order():
    text = "1.2.3.4:80\n1.2.3.4:80\n5.6.7.8:3128"

    candidates = extract_proxy_candidates(text)
    assert [candidate.address for candidate in candidates] == ["1.2.3.4:80", "5.6.7.8:3128"]
