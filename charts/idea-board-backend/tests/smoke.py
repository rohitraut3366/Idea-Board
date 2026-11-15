import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4

backend_url = os.environ["BACKEND_URL"]

with urlopen(f"{backend_url}/health", timeout=10) as response:
    assert response.status == 200
content = f"Helm smoke test {uuid4().hex}"
request = Request(
    f"{backend_url}/api/ideas",
    data=json.dumps({"content": content}).encode(),
    headers={"Content-Type": "application/json"},
)
with urlopen(request, timeout=10) as response:
    assert response.status == 201
    idea = json.load(response)
try:
    with urlopen(f"{backend_url}/api/ideas?limit=100", timeout=10) as response:
        assert idea in json.load(response)
finally:
    request = Request(f"{backend_url}/api/ideas/{idea['id']}", method="DELETE")
    with urlopen(request, timeout=10) as response:
        assert response.status == 204
print("Backend health, create, read, and delete passed")
