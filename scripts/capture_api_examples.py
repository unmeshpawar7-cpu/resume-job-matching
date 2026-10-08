"""Run the real API in-process (offline providers, temporary SQLite) and write
``docs/api-examples.md`` with actual requests and responses.

    python scripts/capture_api_examples.py

Also prints the score-breakdown table used in the README. Nothing is mocked: the app,
parser, scoring engine, hashing embeddings and the OfflineTemplateProvider all run for real.
Long arrays are truncated for readability (marked in the document).
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resume_matching.core.config import ScoringSettings, Settings  # noqa: E402
from resume_matching.main import create_app  # noqa: E402

OUT = ROOT / "docs" / "api-examples.md"
TODAY = date(2026, 10, 8)


def trim(value: Any, limit: int = 4) -> Any:
    if isinstance(value, list):
        return [trim(v, limit) for v in value[:limit]]
    if isinstance(value, dict):
        return {k: trim(v, limit) for k, v in value.items()}
    return value


def block(obj: Any) -> str:
    return "```json\n" + json.dumps(obj, indent=2) + "\n```\n"


async def main() -> None:
    tmp = tempfile.mkdtemp()
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp}/examples.db",
        jwt_secret="example-secret-for-docs-0123456789abcdef",
        bcrypt_rounds=4,
        log_level="WARNING",
    )
    app = create_app(settings, ScoringSettings(_env_file=None), today=lambda: TODAY)
    md: list[str] = [
        "# API examples\n",
        "Captured from a real in-process run by `scripts/capture_api_examples.py` with the "
        "default **offline** providers (`LLM_PROVIDER=offline`, `EMBEDDING_PROVIDER=hashing`) "
        f"and a fixed date of {TODAY.isoformat()}. IDs and tokens differ per run. Arrays longer "
        "than four items are truncated for readability.\n",
        "All examples assume `export API=http://localhost:8000`.\n",
    ]
    breakdown: list[str] = []
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api") as c:
            reg = await c.post(
                "/api/auth/register",
                json={"email": "recruiter@example.com", "password": "correct-horse-battery"},
            )
            md += [
                "## Register\n",
                "```bash\ncurl -s -X POST $API/api/auth/register -H 'Content-Type: application/json' \\\n"
                '  -d \'{"email":"recruiter@example.com","password":"correct-horse-battery"}\'\n```\n',
                f"`{reg.status_code} Created`\n",
                block(reg.json()),
            ]
            tok = await c.post(
                "/api/auth/token",
                json={"email": "recruiter@example.com", "password": "correct-horse-battery"},
            )
            token = tok.json()["data"]["accessToken"]
            shown = tok.json()
            shown["data"]["accessToken"] = token[:24] + "...(truncated)"
            md += [
                "## Get a token\n",
                "```bash\nTOKEN=$(curl -s -X POST $API/api/auth/token -H 'Content-Type: application/json' \\\n"
                '  -d \'{"email":"recruiter@example.com","password":"correct-horse-battery"}\' | jq -r .data.accessToken)\n```\n',
                block(shown),
            ]
            h = {"Authorization": f"Bearer {token}"}

            uploads = {}
            for name in (
                "daniel_okafor_ai_backend.txt",
                "jordan_lee_junior_web.txt",
                "sofia_alvarez_data_engineer.txt",
                "maya_chen_ml_engineer.docx",
                "rohan_deshpande_dotnet_backend.pdf",
            ):
                path = ROOT / "samples" / "resumes" / name
                r = await c.post(
                    "/api/resumes", files={"file": (name, path.read_bytes())}, headers=h
                )
                uploads[name] = r
            first = uploads["daniel_okafor_ai_backend.txt"]
            md += [
                "## Upload a resume\n",
                '```bash\ncurl -s -X POST $API/api/resumes -H "Authorization: Bearer $TOKEN" \\\n'
                "  -F file=@samples/resumes/daniel_okafor_ai_backend.txt\n```\n",
                f"`{first.status_code} Created`, `Location: {first.headers['location']}`\n",
                block(trim(first.json())),
            ]
            dup = await c.post(
                "/api/resumes",
                files={
                    "file": (
                        "again.txt",
                        (ROOT / "samples/resumes/daniel_okafor_ai_backend.txt").read_bytes(),
                    )
                },
                headers=h,
            )
            bad = await c.post("/api/resumes", files={"file": ("cv.exe", b"MZ")}, headers=h)
            md += [
                "### Errors\n",
                f"Same file again -> `{dup.status_code}`\n",
                block(dup.json()),
                f"Unsupported type -> `{bad.status_code}`\n",
                block(bad.json()),
            ]

            jobs = {}
            for name in ("ai_backend_engineer.json", "dotnet_backend_developer.json"):
                body = json.loads((ROOT / "samples" / "jobs" / name).read_text())
                jobs[name] = await c.post("/api/jobs", json=body, headers=h)
            job = jobs["ai_backend_engineer.json"]
            md += [
                "## Create a job\n",
                '```bash\ncurl -s -X POST $API/api/jobs -H "Authorization: Bearer $TOKEN" \\\n'
                "  -H 'Content-Type: application/json' -d @samples/jobs/ai_backend_engineer.json\n```\n",
                f"`{job.status_code} Created`\n",
                block(trim(job.json(), 6)),
            ]

            resume_id = first.json()["data"]["id"]
            job_id = job.json()["data"]["id"]
            analyze = await c.post(
                "/api/matching/analyze", json={"resumeId": resume_id, "jobId": job_id}, headers=h
            )
            again = await c.post(
                "/api/matching/analyze", json={"resumeId": resume_id, "jobId": job_id}, headers=h
            )
            md += [
                "## Analyze a match\n",
                '```bash\ncurl -s -X POST $API/api/matching/analyze -H "Authorization: Bearer $TOKEN" \\\n'
                f'  -H \'Content-Type: application/json\' -d \'{{"resumeId":"{resume_id}","jobId":"{job_id}"}}\'\n```\n',
                f"`{analyze.status_code} Created` (the same call again returns "
                f"`{again.status_code}` with the same `id` - idempotent per scoring version)\n",
                block(trim(analyze.json(), 6)),
            ]
            m = analyze.json()["data"]
            breakdown.append(
                "| Component | Score | Weight | Effective weight | Contribution | Evidence |"
            )
            breakdown.append("|---|---:|---:|---:|---:|---|")
            for comp in m["breakdown"]:
                score = "n/a" if comp["score"] is None else f"{comp['score']:g}"
                breakdown.append(
                    f"| {comp['label']} | {score} | {comp['weight']:g} | "
                    f"{comp['effectiveWeight']:.2f} | {comp['contribution']:g} | {comp['summary']} |"
                )
            breakdown.append(
                f"| **Overall** | **{m['matchPercent']:g}** | | | | verdict: {m['verdict']} |"
            )

            rohan = uploads["rohan_deshpande_dotnet_backend.pdf"].json()["data"]["id"]
            ko = await c.post(
                "/api/matching/analyze", json={"resumeId": rohan, "jobId": job_id}, headers=h
            )
            kd = ko.json()["data"]
            md += [
                "### Knock-out example (.NET resume vs the Python JD)\n",
                "Abbreviated to the fields that show the cap:\n",
                block(
                    {
                        "matchPercent": kd["matchPercent"],
                        "rawScore": kd["rawScore"],
                        "knockouts": kd["knockouts"],
                        "missingRequired": [s["name"] for s in kd["skills"]["missingRequired"]],
                        "explanation": kd["explanation"],
                    }
                ),
            ]

            get = await c.get(f"/api/matching/{m['id']}", headers=h)
            md += [
                "## Get a stored match\n",
                f'```bash\ncurl -s $API/api/matching/{m["id"]} -H "Authorization: Bearer $TOKEN"\n```\n',
                f"`{get.status_code} OK` - same payload as above.\n",
            ]

            dotnet_id = jobs["dotnet_backend_developer.json"].json()["data"]["id"]
            ranking = await c.get(
                f"/api/candidates/ranking?job_id={dotnet_id}&page=1&pageSize=5", headers=h
            )
            md += [
                "## Rank candidates for a job\n",
                f'```bash\ncurl -s "$API/api/candidates/ranking?job_id={dotnet_id}&page=1&pageSize=5" \\\n'
                '  -H "Authorization: Bearer $TOKEN"\n```\n',
                block(ranking.json()),
            ]
            listing = await c.get("/api/resumes?page=1&pageSize=2", headers=h)
            md += ["## List resumes (paginated)\n", block(trim(listing.json(), 3))]

            unauth = await c.get("/api/resumes")
            invalid = await c.post("/api/jobs", json={"title": "x"}, headers=h)
            md += [
                "## Error envelope\n",
                f"No token -> `{unauth.status_code}`\n",
                block(unauth.json()),
                f"Validation -> `{invalid.status_code}`\n",
                block(invalid.json()),
            ]
            health = await c.get("/health/ready")
            md += ["## Health\n", block(health.json())]

    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}\n")
    print("\n".join(breakdown))


if __name__ == "__main__":
    asyncio.run(main())
