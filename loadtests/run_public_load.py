"""Read-only HTTP load probe for a deployed Gather HQs site."""

import argparse
import concurrent.futures
import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request


def percentile(values, percentile_value):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil((percentile_value / 100) * len(ordered)) - 1)
    return ordered[index]


def request_once(url, timeout):
    started = time.perf_counter()
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Gather-HQs-launch-load-probe/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            status = response.status
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"seconds": time.perf_counter() - started, "error": str(exc)}
    return {
        "seconds": time.perf_counter() - started,
        "status": status,
        "error": "" if 200 <= status < 400 else f"HTTP {status}",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run a read-only launch-scale probe against public pages."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        default=[],
        help="Path to include; repeat for multiple routes.",
    )
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--p95-limit", type=float, default=2.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    options = parser.parse_args()
    if options.concurrency <= 0 or options.requests <= 0:
        parser.error("--concurrency and --requests must be positive")
    paths = options.paths or ["/", "/events/", "/health/live/"]
    base_url = options.base_url.rstrip("/") + "/"
    urls = [urllib.parse.urljoin(base_url, path.lstrip("/")) for path in paths]

    # Warm application and connection paths without including them in measurements.
    for url in urls:
        request_once(url, options.timeout)

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=options.concurrency
    ) as executor:
        futures = [
            executor.submit(request_once, urls[index % len(urls)], options.timeout)
            for index in range(options.requests)
        ]
        results = [future.result() for future in futures]
    elapsed = time.perf_counter() - started
    durations = [result["seconds"] for result in results]
    failures = [result for result in results if result["error"]]
    p95 = percentile(durations, 95)
    error_rate = len(failures) / len(results)
    passed = p95 <= options.p95_limit and error_rate <= options.max_error_rate
    payload = {
        "ok": passed,
        "base_url": base_url,
        "paths": paths,
        "concurrency": options.concurrency,
        "requests": len(results),
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(len(results) / elapsed, 2),
        "latency_seconds": {
            "mean": round(statistics.fmean(durations), 3),
            "p50": round(percentile(durations, 50), 3),
            "p95": round(p95, 3),
            "max": round(max(durations), 3),
        },
        "error_count": len(failures),
        "error_rate": round(error_rate, 4),
        "thresholds": {
            "p95_seconds": options.p95_limit,
            "max_error_rate": options.max_error_rate,
        },
        "sample_errors": [result["error"] for result in failures[:10]],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
