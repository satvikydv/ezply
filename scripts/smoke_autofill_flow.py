import json
from fastapi.testclient import TestClient

from ezply.main import app


def main() -> None:
    with TestClient(app) as client:
        body = {"display_name": "Primary Autofill", "passphrase": "test-pass", "profile": {"name": "Alice", "email": "alice@example.com"}}
        r = client.put("/autofill", json=body)
        print("put status", r.status_code, r.json())

        r2 = client.post("/autofill/export", json={"passphrase": "test-pass"})
        print("export status", r2.status_code, r2.json())


if __name__ == "__main__":
    main()
