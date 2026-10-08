from __future__ import annotations

from tests.conftest import ScriptedLLM, create_job, register_and_login, upload

RESUMES = [
    "daniel_okafor_ai_backend.txt",
    "jordan_lee_junior_web.txt",
    "sofia_alvarez_data_engineer.txt",
    "maya_chen_ml_engineer.docx",
    "rohan_deshpande_dotnet_backend.pdf",
]


async def _seed(client, headers, job="ai_backend_engineer.json"):
    ids = {name: (await upload(client, headers, name))["id"] for name in RESUMES}
    return ids, (await create_job(client, headers, job))["id"]


async def test_ranking_batch_computes_and_orders(client, auth):
    ids, job_id = await _seed(client, auth)
    r = await client.get(f"/api/candidates/ranking?job_id={job_id}", headers=auth)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["candidatesConsidered"] == 5
    assert data["newlyComputed"] == 5
    items = data["items"]
    assert [i["rank"] for i in items] == [1, 2, 3, 4, 5]
    scores = [i["matchPercent"] for i in items]
    assert scores == sorted(scores, reverse=True)
    assert items[0]["resumeId"] == ids["daniel_okafor_ai_backend.txt"]
    assert items[-1]["resumeId"] == ids["jordan_lee_junior_web.txt"]
    assert "missing_critical_skill" in items[-1]["knockouts"]
    assert all(1 <= len(i["topReasons"]) <= 3 for i in items)

    again = (await client.get(f"/api/candidates/ranking?job_id={job_id}", headers=auth)).json()
    assert again["data"]["newlyComputed"] == 0
    assert [i["resumeId"] for i in again["data"]["items"]] == [i["resumeId"] for i in items]


async def test_ranking_pagination_and_min_score(client, auth):
    _, job_id = await _seed(client, auth, "dotnet_backend_developer.json")
    page = (
        await client.get(f"/api/candidates/ranking?job_id={job_id}&page=2&pageSize=2", headers=auth)
    ).json()["data"]
    assert page["totalCount"] == 5
    assert page["totalPages"] == 3
    assert [i["rank"] for i in page["items"]] == [3, 4]
    filtered = (
        await client.get(f"/api/candidates/ranking?job_id={job_id}&min_score=60", headers=auth)
    ).json()["data"]
    assert filtered["totalCount"] == 1
    assert filtered["items"][0]["filename"] == "rohan_deshpande_dotnet_backend.pdf"


async def test_ranking_errors(client, auth):
    assert (await client.get("/api/candidates/ranking", headers=auth)).status_code == 422
    r = await client.get("/api/candidates/ranking?job_id=missing", headers=auth)
    assert r.status_code == 404
    _, job_id = await _seed(client, auth)
    bad = await client.get(f"/api/candidates/ranking?job_id={job_id}&min_score=101", headers=auth)
    assert bad.status_code == 422


async def test_ranked_match_gets_llm_narrative_on_analyze_without_score_change(app_factory):
    llm = ScriptedLLM()
    async with app_factory(llm=llm) as client:
        headers = await register_and_login(client)
        _ids, job_id = await _seed(client, headers)
        ranking = (
            await client.get(f"/api/candidates/ranking?job_id={job_id}", headers=headers)
        ).json()["data"]
        top = ranking["items"][0]
        assert llm.requests == []  # batch ranking never calls the LLM
        deferred = (await client.get(f"/api/matching/{top['matchId']}", headers=headers)).json()
        assert deferred["data"]["explanation"]["source"] == "deferred_template"

        r = await client.post(
            "/api/matching/analyze",
            json={"resumeId": top["resumeId"], "jobId": job_id},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == top["matchId"]
        assert data["explanation"]["source"] == "llm"
        assert data["matchPercent"] == top["matchPercent"]
        assert len(llm.requests) == 1


async def test_ranking_uses_vector_preselection_above_pool(app_factory):
    async with app_factory(ranking_candidate_pool=2) as client:
        headers = await register_and_login(client)
        ids, job_id = await _seed(client, headers, "dotnet_backend_developer.json")
        data = (
            await client.get(f"/api/candidates/ranking?job_id={job_id}", headers=headers)
        ).json()["data"]
        assert data["candidatesConsidered"] == 2
        assert ids["rohan_deshpande_dotnet_backend.pdf"] in {i["resumeId"] for i in data["items"]}
