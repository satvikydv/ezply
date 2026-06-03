from fastapi.testclient import TestClient

from ezply.main import app


def main() -> None:
    with TestClient(app) as client:
        # Ensure there's at least one job or create a dummy
        r = client.get('/jobs')
        jobs = r.json().get('jobs', [])
        if not jobs:
            print('No jobs to test assisted apply against. Import some Greenhouse boards or add jobs.')
            return

        job_id = jobs[0]['id']
        body = {'job_id': job_id, 'passphrase': 'test-pass', 'confirm_submit': False}
        r2 = client.post('/apply/assist', json=body)
        print('assist status', r2.status_code)
        print('assist resp', r2.json())


if __name__ == '__main__':
    main()
