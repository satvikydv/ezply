from fastapi.testclient import TestClient

from ezply.main import app


def main() -> None:
    with TestClient(app) as client:
        initial_resume = client.get("/resume")
        print("initial_resume_status", initial_resume.status_code)

        saved = client.put(
            "/resume",
            json={"display_name": "Primary Resume", "resume_text": "Python FastAPI SQL internship"},
        )
        print("saved_resume_status", saved.status_code)
        print("saved_resume", saved.json())

        ranked = client.post("/jobs/rank", json={"limit": 5})
        print("rank_status", ranked.status_code)
        print("rank_response", ranked.json())


if __name__ == "__main__":
    main()
