import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4

backend_url = os.environ["BACKEND_URL"]
frontend_url = os.environ["FRONTEND_URL"]

with urlopen(f"{backend_url}/health", timeout=10) as response:
    assert response.status == 200
with urlopen(frontend_url, timeout=10) as response:
    assert b'<div id="root">' in response.read()

content = f"Helm smoke test {uuid4().hex}"
request = Request(
    f"{frontend_url}/api/ideas",
    data=json.dumps({"content": content}).encode(),
    headers={"Content-Type": "application/json"},
)
with urlopen(request, timeout=10) as response:
    assert response.status == 201
    idea = json.load(response)
try:
    with urlopen(f"{frontend_url}/api/ideas?limit=100", timeout=10) as response:
        assert idea in json.load(response)
finally:
    request = Request(f"{frontend_url}/api/ideas/{idea['id']}", method="DELETE")
    with urlopen(request, timeout=10) as response:
        assert response.status == 204
print("Backend health, frontend, API proxy, create, read, and delete passed")
