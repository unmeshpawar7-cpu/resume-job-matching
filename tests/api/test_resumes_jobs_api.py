from __future__ import annotations

import io
import zipfile

from tests.conftest import create_job, register_and_login, sample_resume, upload


async def test_upload_txt_returns_parsed_profile(client, auth):
    data = await upload(client, auth, "daniel_okafor_ai_backend.txt")
    profile = data["profile"]
    assert data["fileType"] == "txt"
    assert profile["currentTitle"] == "Senior Backend Engineer"
    assert profile["seniority"] == "senior"
    assert profile["experience"]["totalYears"] == 8.4
    names = {s["name"] for s in profile["skills"]}
    assert {"Python", "FastAPI", "pgvector", "Kubernetes"} <= names
    assert "header" not in {s["type"] for s in profile["sections"]}


async def test_upload_docx_and_pdf(client, auth):
    docx = await upload(client, auth, "maya_chen_ml_engineer.docx")
    pdf = await upload(client, auth, "rohan_deshpande_dotnet_backend.pdf")
    assert docx["fileType"] == "docx"
    assert docx["profile"]["currentTitle"] == "Machine Learning Engineer"
    assert pdf["fileType"] == "pdf"
    assert pdf["pageCount"] == 1
    assert {"C#", ".NET", "ASP.NET Core"} <= {s["name"] for s in pdf["profile"]["skills"]}


async def test_upload_location_get_and_duplicate_409(client, auth):
    filename, payload = sample_resume("jordan_lee_junior_web.txt")
    r = await client.post("/api/resumes", files={"file": (filename, payload)}, headers=auth)
    assert r.status_code == 201
    location = r.headers["location"]
    got = await client.get(location, headers=auth)
    assert got.status_code == 200
    assert got.json()["data"]["id"] == r.json()["data"]["id"]

    dup = await client.post("/api/resumes", files={"file": ("copy.txt", payload)}, headers=auth)
    assert dup.status_code == 409
    assert dup.json()["errors"][0]["field"] == "file"


async def test_upload_rejects_bad_types_and_sizes(client, auth):
    r = await client.post("/api/resumes", files={"file": ("cv.exe", b"MZ....")}, headers=auth)
    assert r.status_code == 415
    fake_pdf = await client.post(
        "/api/resumes", files={"file": ("cv.pdf", b"not really a pdf at all")}, headers=auth
    )
    assert fake_pdf.status_code == 415
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "x")
    not_docx = await client.post(
        "/api/resumes", files={"file": ("cv.docx", buf.getvalue())}, headers=auth
    )
    assert not_docx.status_code == 415
    too_big = await client.post(
        "/api/resumes", files={"file": ("cv.txt", b"a" * 250_000)}, headers=auth
    )
    assert too_big.status_code == 413
    empty = await client.post("/api/resumes", files={"file": ("cv.txt", b"")}, headers=auth)
    assert empty.status_code == 422
    tiny = await client.post("/api/resumes", files={"file": ("cv.txt", b"hello")}, headers=auth)
    assert tiny.status_code == 422


async def test_resume_pagination(client, auth):
    for name in ("daniel_okafor_ai_backend.txt", "jordan_lee_junior_web.txt", "sofia_alvarez_data_engineer.txt"):  # fmt: skip
        await upload(client, auth, name)
    page1 = (await client.get("/api/resumes?page=1&pageSize=2", headers=auth)).json()["data"]
    assert page1["totalCount"] == 3
    assert page1["totalPages"] == 2
    assert len(page1["items"]) == 2
    page2 = (await client.get("/api/resumes?page=2&page_size=2", headers=auth)).json()["data"]
    assert len(page2["items"]) == 1
    ids = {i["id"] for i in page1["items"]} | {i["id"] for i in page2["items"]}
    assert len(ids) == 3
    capped = (await client.get("/api/resumes?pageSize=1000", headers=auth)).json()["data"]
    assert capped["pageSize"] == 100
    bad = await client.get("/api/resumes?page=0", headers=auth)
    assert bad.status_code == 422


async def test_delete_permissions_and_cascade(client, auth, admin_auth):
    resume = await upload(client, auth, "daniel_okafor_ai_backend.txt")
    job = await create_job(client, auth, "ai_backend_engineer.json")
    analyzed = await client.post(
        "/api/matching/analyze", json={"resumeId": resume["id"], "jobId": job["id"]}, headers=auth
    )
    match_id = analyzed.json()["data"]["id"]

    other = await register_and_login(client, "other@example.com", "other-password-1")
    assert (await client.delete(f"/api/resumes/{resume['id']}", headers=other)).status_code == 403
    assert (await client.delete(f"/api/resumes/{resume['id']}", headers=auth)).status_code == 204
    assert (await client.get(f"/api/resumes/{resume['id']}", headers=auth)).status_code == 404
    assert (await client.get(f"/api/matching/{match_id}", headers=auth)).status_code == 404
    assert (await client.delete(f"/api/resumes/{resume['id']}", headers=auth)).status_code == 404

    second = await upload(client, auth, "jordan_lee_junior_web.txt")
    assert (
        await client.delete(f"/api/resumes/{second['id']}", headers=admin_auth)
    ).status_code == 204


async def test_jobs_create_get_list(client, auth):
    job = await create_job(client, auth, "ai_backend_engineer.json")
    analysis = job["analysis"]
    assert analysis["minYears"] == 5
    assert analysis["seniority"] == "senior"
    by_name = {r["name"]: r["importance"] for r in analysis["requirements"]}
    assert by_name["Python"] == "critical"
    assert by_name["FastAPI"] == "critical"
    assert by_name["PostgreSQL"] == "required"
    assert by_name["Kubernetes"] == "nice_to_have"
    assert by_name["Kafka"] == "nice_to_have"

    await create_job(client, auth, "dotnet_backend_developer.json")
    listing = (await client.get("/api/jobs?pageSize=1", headers=auth)).json()["data"]
    assert listing["totalCount"] == 2
    assert listing["items"][0]["title"] == ".NET Backend Developer"
    got = await client.get(f"/api/jobs/{job['id']}", headers=auth)
    assert got.json()["data"]["title"] == job["title"]
    assert (await client.get("/api/jobs/does-not-exist", headers=auth)).status_code == 404


async def test_job_validation(client, auth):
    r = await client.post("/api/jobs", json={"title": "x", "description": "short"}, headers=auth)
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} == {"title", "description"}
