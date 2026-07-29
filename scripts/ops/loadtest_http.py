from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def main() -> None:
    args = parse_args()
    headers = {}
    for item in args.header:
        name, _, value = item.partition(":")
        if name and value:
            headers[name.strip()] = value.strip()

    paths = [item.strip() for item in args.path.split(",") if item.strip()]
    latencies: list[float] = []
    errors = 0
    started = time.perf_counter()
    semaphore = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout) as client:
        tasks = [
            _request(client, paths[index % len(paths)], headers, semaphore, latencies)
            for index in range(args.requests)
        ]
        results = await asyncio.gather(*tasks)
        errors = sum(1 for ok in results if not ok)

    elapsed = time.perf_counter() - started
    latencies.sort()
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    avg = statistics.mean(latencies) if latencies else 0

    print(f"requests={args.requests}")
    print(f"concurrency={args.concurrency}")
    print(f"errors={errors}")
    print(f"error_rate={errors / args.requests:.4f}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"qps={args.requests / elapsed:.2f}")
    print(f"avg_ms={avg:.2f}")
    print(f"p95_ms={p95:.2f}")
    print(f"p99_ms={p99:.2f}")


async def _request(
    client: httpx.AsyncClient,
    path: str,
    headers: dict[str, str],
    semaphore: asyncio.Semaphore,
    latencies: list[float],
) -> bool:
    async with semaphore:
        started = time.perf_counter()
        try:
            response = await client.get(path, headers=headers)
            return response.status_code < 500
        except Exception:
            return False
        finally:
            latencies.append((time.perf_counter() - started) * 1000)


def percentile(values: list[float], rank: int) -> float:
    if not values:
        return 0
    index = min(len(values) - 1, max(0, round((rank / 100) * len(values)) - 1))
    return values[index]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple HTTP load test for smoke baselines.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--path", default="/", help="Comma-separated GET paths.")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--header", action="append", default=[], help="Header as 'Name: value'.")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main())
