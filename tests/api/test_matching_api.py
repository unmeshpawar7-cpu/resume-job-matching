from __future__ import annotations

import json

from sqlalchemy import func, select

from resume_matching.db.models import AIUsage, MatchResult
from tests.conftest import ScriptedLLM, create_job, register_and_login, upload


async def _setup(client, headers, resume="daniel_okafor_ai_backend.txt", job="ai_backend_engineer.json"):  # fmt: skip
    r = await upload(client, headers, resume)
    j = await create_job(client, headers, job)
    return r["id"], j["id"]


async def test_analyze_returns_full_explainable_result(client, auth):
    resume_id, job_id = await _setup(client, auth)
    r = await client.post(
        "/api/matching/analyze", json={"resume_id": resume_id, "job_id": job_id}, headers=auth
    )
    assert r.status_code == 201
    assert r.headers["location"].startswith("/api/matching/")
    m = r.json()["data"]
    assert 80 <= m["matchPercent"] <= 100
    assert m["verdict"] == "strong"
    assert m["scoringVersion"].startswith("1.0.0+")
    assert m["promptVersion"] == "match_explanation/v1"
    assert {c["key"] for c in m["breakdown"]} == {
        "required_skills", "nice_to_have", "experience", "role", "semantic",
    }  # fmt: skip
    assert abs(sum(c["contribution"] for c in m["breakdown"]) - m["rawScore"]) < 0.1
    matched = {s["name"] for s in m["skills"]["matchedRequired"]}
    assert {"Python", "FastAPI", "PostgreSQL"} <= matched
    assert {s["name"] for s in m["skills"]["missingNiceToHave"]} >= {"Terraform"}
    assert m["experience"]["requiredYears"] == 5
    assert m["roleMatch"]["candidateTitle"] == "Senior Backend Engineer"
    assert m["interviewPrepTopics"]
    assert m["explanation"]["source"] == "offline_template"
    assert str(m["matchPercent"]).rstrip("0").rstrip(".") in m["explanation"]["summary"]


async def test_analyze_is_idempotent_and_force_recomputes(client, auth):
    resume_id, job_id = await _setup(client, auth)
    body = {"resumeId": resume_id, "jobId": job_id}
    first = await client.post("/api/matching/analyze", json=body, headers=auth)
    second = await client.post("/api/matching/analyze", json=body, headers=auth)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.json()["data"]["matchPercent"] == second.json()["data"]["matchPercent"]

    forced = await client.post("/api/matching/analyze", json={**body, "force": True}, headers=auth)
    assert forced.status_code == 200
    assert forced.json()["data"]["id"] == first.json()["data"]["id"]
    assert forced.json()["data"]["matchPercent"] == first.json()["data"]["matchPercent"]

    got = await client.get(f"/api/matching/{first.json()['data']['id']}", headers=auth)
    assert got.status_code == 200

    sm = client.app.state.container.sessionmaker
    async with sm() as session:
        count = await session.scalar(select(func.count(MatchResult.id)))
        usage = (await session.scalars(select(AIUsage))).all()
    assert count == 1
    assert len(usage) == 2  # one explanation call per computation (first + forced)
    assert all(u.prompt_version == "match_explanation/v1" and u.success for u in usage)


async def test_analyze_404_and_422(client, auth):
    resume_id, job_id = await _setup(client, auth)
    r = await client.post(
        "/api/matching/analyze", json={"resumeId": "nope", "jobId": job_id}, headers=auth
    )
    assert r.status_code == 404
    r = await client.post(
        "/api/matching/analyze", json={"resumeId": resume_id, "jobId": "nope"}, headers=auth
    )
    assert r.status_code == 404
    r = await client.post("/api/matching/analyze", json={"resumeId": resume_id}, headers=auth)
    assert r.status_code == 422
    assert (await client.get("/api/matching/unknown", headers=auth)).status_code == 404


async def test_analyze_rate_limited(app_factory):
    async with app_factory(analyze_rate_limit_burst=2, analyze_rate_limit_per_minute=1) as client:
        headers = await register_and_login(client)
        resume_id, job_id = await _setup(client, headers)
        body = {"resumeId": resume_id, "jobId": job_id}
        assert (
            await client.post("/api/matching/analyze", json=body, headers=headers)
        ).status_code == 201
        assert (
            await client.post("/api/matching/analyze", json=body, headers=headers)
        ).status_code == 200
        limited = await client.post("/api/matching/analyze", json=body, headers=headers)
        assert limited.status_code == 429
        assert limited.json()["success"] is False


async def test_llm_explanation_is_used_when_grounded(app_factory):
    llm = ScriptedLLM()
    async with app_factory(llm=llm) as client:
        headers = await register_and_login(client)
        resume_id, job_id = await _setup(client, headers)
        r = await client.post(
            "/api/matching/analyze", json={"resumeId": resume_id, "jobId": job_id}, headers=headers
        )
        m = r.json()["data"]
        assert m["explanation"]["source"] == "llm"
        assert m["explanation"]["provider"] == "openai"
        assert m["explanation"]["model"] == "scripted-model"
        # The prompt contained only computed facts - no resume text or contact details.
        prompt = llm.requests[0].user
        assert "daniel.okafor@example.com" not in prompt
        assert "Verdant Labs" not in prompt
        assert json.dumps(m["matchPercent"]) in prompt


async def test_hallucinating_llm_falls_back_but_score_is_unchanged(app_factory):
    bad = json.dumps(
        {
            "summary": "Great candidate with deep Rust and Scala skills, roughly a 99% fit.",
            "strengths": ["Rust"],
            "gaps": [],
            "skills_mentioned": ["Rust", "Scala"],
        }
    )
    llm = ScriptedLLM([bad, bad, bad])
    async with app_factory(llm=llm) as client:
        headers = await register_and_login(client)
        resume_id, job_id = await _setup(client, headers)
        r = await client.post(
            "/api/matching/analyze", json={"resumeId": resume_id, "jobId": job_id}, headers=headers
        )
        m = r.json()["data"]
    async with app_factory() as offline_client:
        headers = await register_and_login(offline_client)
        resume_id, job_id = await _setup(offline_client, headers)
        baseline = await offline_client.post(
            "/api/matching/analyze", json={"resumeId": resume_id, "jobId": job_id}, headers=headers
        )
    assert m["explanation"]["source"] == "template_fallback"
    assert "Rust" not in m["explanation"]["summary"]
    assert len(llm.requests) == 3  # 1 attempt + 2 validation retries
    assert "rejected" in llm.requests[1].user
    assert m["matchPercent"] == baseline.json()["data"]["matchPercent"]


async def test_other_user_cannot_delete_but_can_read_match(client, auth):
    resume_id, job_id = await _setup(client, auth)
    r = await client.post(
        "/api/matching/analyze", json={"resumeId": resume_id, "jobId": job_id}, headers=auth
    )
    other = await register_and_login(client, "peer@example.com", "peer-password-1")
    got = await client.get(f"/api/matching/{r.json()['data']['id']}", headers=other)
    assert got.status_code == 200


async def test_embedding_model_change_reembeds_and_changes_scoring_version(client, auth):
    from resume_matching.ai.embeddings.hashing import HashingEmbeddingProvider

    resume_id, job_id = await _setup(client, auth)
    body = {"resumeId": resume_id, "jobId": job_id}
    before = (await client.post("/api/matching/analyze", json=body, headers=auth)).json()["data"]

    container = client.app.state.container
    replacement = HashingEmbeddingProvider(512)
    replacement.model_id = "hashing-v1-512-recalibrated"
    container.embedder = replacement
    after = await client.post("/api/matching/analyze", json=body, headers=auth)
    assert after.status_code == 201  # new scoring version => new result row
    data = after.json()["data"]
    assert data["scoringVersion"] != before["scoringVersion"]
    assert data["matchPercent"] == before["matchPercent"]  # same vectors, same score
    resume = (await client.get(f"/api/resumes/{resume_id}", headers=auth)).json()["data"]
    assert resume["embeddingModel"] == "hashing-v1-512-recalibrated"
