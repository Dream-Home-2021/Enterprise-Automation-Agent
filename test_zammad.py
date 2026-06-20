import httpx, asyncio, json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

async def t():
    token = "eyk41yu-0irE10CZT9hTz60okNqtINyrWf7M9oyhFooeNwjGxkxWUoMe8qokEiEL"
    headers = {"Authorization": f"Token token={token}"}
    client = httpx.AsyncClient(mounts={}, timeout=30)

    # Test multiple times to rule out caching
    for i in range(3):
        r = await client.get("http://localhost:8080/api/v1/tickets", headers=headers)
        print(f"Attempt {i+1}: {r.status_code}")
        if r.status_code != 200:
            print(f"  Body: {r.text[:300]}")

    # Check what the actual response body says
    r = await client.get("http://localhost:8080/api/v1/tickets", headers=headers)
    print(f"\nFinal: {r.status_code}")
    print(f"Headers: {dict(r.headers)}")
    print(f"Body: {r.text[:500]}")

asyncio.run(t())
