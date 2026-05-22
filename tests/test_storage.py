import json
from pathlib import Path

import pytest

from proxy_pool.models import empty_proxy_document
from proxy_pool.storage import read_proxy_document, write_proxy_document


def test_read_proxy_document_returns_empty_for_missing_file(tmp_path: Path):
    assert read_proxy_document(tmp_path / "missing.json") == empty_proxy_document()


def test_read_proxy_document_returns_empty_for_malformed_file(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text("{", encoding="utf-8")

    assert read_proxy_document(target) == empty_proxy_document()


def test_read_proxy_document_returns_empty_for_non_dict_file(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text("[]", encoding="utf-8")

    assert read_proxy_document(target) == empty_proxy_document()


def test_read_proxy_document_returns_empty_for_non_v2_file(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text('{"total_count_of_proxies": 1, "http": [], "socks4": [], "socks5": []}', encoding="utf-8")

    assert read_proxy_document(target) == empty_proxy_document()


def test_read_proxy_document_normalizes_v2_items_and_recomputes_total(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        """
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 99,
  "items": [
    "bad",
    {
      "endpoint": "1.2.3.4:8080",
      "source_protocol": "http",
      "usable_as": ["https", "http", "https"],
      "quality": {
        "score": 999,
        "success_rate": -1,
        "checks_passed": -2,
        "checks_failed": 3.8,
        "avg_latency_ms": -420,
        "last_error": 404
      },
      "network": {
        "exit_ip": "8.8.8.8",
        "country_code": "US",
        "anonymous": true
      },
      "timestamps": {"checked_at": "2026-05-22T12:00:00Z"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    assert read_proxy_document(target) == {
        "version": 2,
        "generated_at": "2026-05-22T12:00:00Z",
        "total": 1,
        "items": [
            {
                "endpoint": "1.2.3.4:8080",
                "source_protocol": "http",
                "usable_as": ["https", "http"],
                "quality": {
                    "score": 100.0,
                    "success_rate": 0.0,
                    "checks_passed": 0,
                    "checks_failed": 3,
                    "avg_latency_ms": 0,
                    "last_error": "404",
                },
                "network": {
                    "exit_ip": "8.8.8.8",
                    "country_code": "US",
                    "anonymous": True,
                },
                "timestamps": {"checked_at": "2026-05-22T12:00:00Z"},
            }
        ],
    }


def test_read_proxy_document_drops_item_with_empty_usable_as(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        """
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 1,
  "items": [
    {
      "endpoint": "1.2.3.4:8080",
      "source_protocol": "http",
      "usable_as": [],
      "quality": {
        "score": 90.8,
        "success_rate": 1.0,
        "checks_passed": 2,
        "checks_failed": 0,
        "avg_latency_ms": 420,
        "last_error": null
      },
      "network": {
        "exit_ip": "8.8.8.8",
        "country_code": "US",
        "anonymous": true
      },
      "timestamps": {"checked_at": "2026-05-22T12:00:00Z"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    assert read_proxy_document(target) == empty_proxy_document(generated_at="2026-05-22T12:00:00Z")


def test_read_proxy_document_drops_item_with_invalid_usable_as(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        """
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 1,
  "items": [
    {
      "endpoint": "1.2.3.4:8080",
      "source_protocol": "http",
      "usable_as": ["http", "bad"],
      "quality": {
        "score": 90.8,
        "success_rate": 1.0,
        "checks_passed": 2,
        "checks_failed": 0,
        "avg_latency_ms": 420,
        "last_error": null
      },
      "network": {
        "exit_ip": "8.8.8.8",
        "country_code": "US",
        "anonymous": true
      },
      "timestamps": {"checked_at": "2026-05-22T12:00:00Z"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    assert read_proxy_document(target) == empty_proxy_document(generated_at="2026-05-22T12:00:00Z")


def test_read_proxy_document_drops_item_with_invalid_exit_ip(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        """
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 1,
  "items": [
    {
      "endpoint": "1.2.3.4:8080",
      "source_protocol": "http",
      "usable_as": ["http"],
      "quality": {
        "score": 90.8,
        "success_rate": 1.0,
        "checks_passed": 2,
        "checks_failed": 0,
        "avg_latency_ms": 420,
        "last_error": null
      },
      "network": {
        "exit_ip": "not-an-ip",
        "country_code": "US",
        "anonymous": true
      },
      "timestamps": {"checked_at": "2026-05-22T12:00:00Z"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    assert read_proxy_document(target) == empty_proxy_document(generated_at="2026-05-22T12:00:00Z")


def test_read_proxy_document_drops_item_with_invalid_endpoint(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        """
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 1,
  "items": [
    {
      "endpoint": "not-an-endpoint",
      "source_protocol": "http",
      "usable_as": ["http"],
      "quality": {
        "score": 90.8,
        "success_rate": 1.0,
        "checks_passed": 2,
        "checks_failed": 0,
        "avg_latency_ms": 420,
        "last_error": null
      },
      "network": {
        "exit_ip": "8.8.8.8",
        "country_code": "US",
        "anonymous": true
      },
      "timestamps": {"checked_at": "2026-05-22T12:00:00Z"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    assert read_proxy_document(target) == empty_proxy_document(generated_at="2026-05-22T12:00:00Z")


@pytest.mark.parametrize("endpoint", ["1.2.3.4:+80", "1.2.3.4: 80", "1.2.3.4:80\n"])
def test_read_proxy_document_drops_item_with_non_canonical_port(endpoint: str, tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        json.dumps(
            {
                "version": 2,
                "generated_at": "2026-05-22T12:00:00Z",
                "total": 1,
                "items": [
                    {
                        "endpoint": endpoint,
                        "source_protocol": "http",
                        "usable_as": ["http"],
                        "quality": {
                            "score": 90.8,
                            "success_rate": 1.0,
                            "checks_passed": 2,
                            "checks_failed": 0,
                            "avg_latency_ms": 420,
                            "last_error": None,
                        },
                        "network": {
                            "exit_ip": "8.8.8.8",
                            "country_code": "US",
                            "anonymous": True,
                        },
                        "timestamps": {"checked_at": "2026-05-22T12:00:00Z"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert read_proxy_document(target) == empty_proxy_document(generated_at="2026-05-22T12:00:00Z")


def test_read_proxy_document_drops_item_with_zero_port_endpoint(tmp_path: Path):
    target = tmp_path / "proxies.json"
    target.write_text(
        """
{
  "version": 2,
  "generated_at": "2026-05-22T12:00:00Z",
  "total": 1,
  "items": [
    {
      "endpoint": "1.2.3.4:0",
      "source_protocol": "http",
      "usable_as": ["http"],
      "quality": {
        "score": 90.8,
        "success_rate": 1.0,
        "checks_passed": 2,
        "checks_failed": 0,
        "avg_latency_ms": 420,
        "last_error": null
      },
      "network": {
        "exit_ip": "8.8.8.8",
        "country_code": "US",
        "anonymous": true
      },
      "timestamps": {"checked_at": "2026-05-22T12:00:00Z"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    assert read_proxy_document(target) == empty_proxy_document(generated_at="2026-05-22T12:00:00Z")


def test_write_proxy_document_normalizes_invalid_generated_at_to_empty_string(tmp_path: Path):
    target = tmp_path / "proxies.json"
    payload = empty_proxy_document(generated_at="2026-05-22T12:00:00Z")
    payload["generated_at"] = 123

    write_proxy_document(target, payload)

    assert json.loads(target.read_text(encoding="utf-8"))["generated_at"] == ""
    assert read_proxy_document(target) == empty_proxy_document()


def test_write_proxy_document_writes_v2_schema_atomically(tmp_path: Path):
    target = tmp_path / "proxies.json"
    payload = empty_proxy_document(generated_at="2026-05-22T12:00:00Z")
    payload["items"].append(
        {
            "endpoint": "1.2.3.4:8080",
            "source_protocol": "http",
            "usable_as": ["http", "https"],
            "quality": {
                "score": 90.8,
                "success_rate": 1.0,
                "checks_passed": 2,
                "checks_failed": 0,
                "avg_latency_ms": 420,
                "last_error": None,
            },
            "network": {
                "exit_ip": "8.8.8.8",
                "country_code": "US",
                "anonymous": True,
            },
            "timestamps": {"checked_at": "2026-05-22T12:00:00Z"},
        }
    )
    payload["total"] = 1

    write_proxy_document(target, payload)

    assert read_proxy_document(target) == payload
    assert not list(tmp_path.glob("*.tmp"))
