# API examples

Captured from a real in-process run by `scripts/capture_api_examples.py` with the default **offline** providers (`LLM_PROVIDER=offline`, `EMBEDDING_PROVIDER=hashing`) and a fixed date of 2026-10-08. IDs and tokens differ per run. Arrays longer than four items are truncated for readability.

All examples assume `export API=http://localhost:8000`.

## Register

```bash
curl -s -X POST $API/api/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"recruiter@example.com","password":"correct-horse-battery"}'
```

`201 Created`

```json
{
  "success": true,
  "data": {
    "id": "4347d989-c395-4d8a-bc5f-66ed22bb6945",
    "email": "recruiter@example.com",
    "role": "recruiter",
    "createdAt": "2026-10-08T14:25:12.975071"
  },
  "message": null
}
```

## Get a token

```bash
TOKEN=$(curl -s -X POST $API/api/auth/token -H 'Content-Type: application/json' \
  -d '{"email":"recruiter@example.com","password":"correct-horse-battery"}' | jq -r .data.accessToken)
```

```json
{
  "success": true,
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIsInR5...(truncated)",
    "tokenType": "bearer",
    "expiresIn": 3600,
    "role": "recruiter"
  },
  "message": null
}
```

## Upload a resume

```bash
curl -s -X POST $API/api/resumes -H "Authorization: Bearer $TOKEN" \
  -F file=@samples/resumes/daniel_okafor_ai_backend.txt
```

`201 Created`, `Location: /api/resumes/bbc2275e-4422-4eb3-924d-ea6cea28189b`

```json
{
  "success": true,
  "data": {
    "id": "bbc2275e-4422-4eb3-924d-ea6cea28189b",
    "filename": "daniel_okafor_ai_backend.txt",
    "fileType": "txt",
    "contentType": "text/plain",
    "sizeBytes": 1344,
    "pageCount": null,
    "checksum": "7f2b6bae41f400f2b27f7345ebf9c0c2cc90973a6657a35ed86c77618f60b491",
    "ownerId": "4347d989-c395-4d8a-bc5f-66ed22bb6945",
    "embeddingModel": "hashing-v1-512",
    "createdAt": "2026-10-08T14:25:13.028660",
    "profile": {
      "parserVersion": "1.0.0",
      "taxonomyVersion": "2026.10.2",
      "sections": [
        {
          "type": "summary",
          "characters": 159
        },
        {
          "type": "skills",
          "characters": 214
        },
        {
          "type": "experience",
          "characters": 760
        },
        {
          "type": "education",
          "characters": 35
        }
      ],
      "skills": [
        {
          "name": "Python",
          "category": "language",
          "mentions": 4,
          "sections": [
            "summary",
            "skills",
            "experience"
          ],
          "surfaceForms": [
            "Python"
          ],
          "evidenced": true,
          "lastUsed": "present",
          "yearsUsed": 6.0,
          "snippets": [
            "Senior backend engineer with 8 years of experience building Python APIs, most recently LLM-powered services. I care about typed, tested and observable systems.",
            "Async Python (asyncio, SQLAlchemy 2.0) services on Kubernetes (EKS) with OpenTelemetry tracing."
          ]
        },
        {
          "name": "Kubernetes",
          "category": "devops",
          "mentions": 3,
          "sections": [
            "skills",
            "experience"
          ],
          "surfaceForms": [
            "Kubernetes",
            "EKS"
          ],
          "evidenced": true,
          "lastUsed": "present",
          "yearsUsed": 4.8,
          "snippets": [
            "Async Python (asyncio, SQLAlchemy 2.0) services on Kubernetes (EKS) with OpenTelemetry tracing."
          ]
        },
        {
          "name": "LLMs",
          "category": "ml_ai",
          "mentions": 3,
          "sections": [
            "summary",
            "skills",
            "experience"
          ],
          "surfaceForms": [
            "LLM",
            "LLMs"
          ],
          "evidenced": true,
          "lastUsed": "present",
          "yearsUsed": 4.8,
          "snippets": [
            "Senior backend engineer with 8 years of experience building Python APIs, most recently LLM-powered services. I care about typed, tested and observable systems.",
            "Designed an LLM gateway in FastAPI with a provider abstraction (OpenAI, Anthropic), retries, timeouts and per-tenant token budgets."
          ]
        },
        {
          "name": "PostgreSQL",
          "category": "database",
          "mentions": 3,
          "sections": [
            "skills",
            "experience"
          ],
          "surfaceForms": [
            "PostgreSQL"
          ],
          "evidenced": true,
          "lastUsed": "present",
          "yearsUsed": 7.2,
          "snippets": [
            "Built a RAG service on PostgreSQL + pgvector with hybrid search and an evaluation suite in pytest.",
            "REST APIs with Django REST Framework and PostgreSQL; Celery and Redis background jobs."
          ]
        }
      ],
      "experience": {
        "totalYears": 8.4,
        "source": "date_ranges",
        "statedYears": 8.0,
        "dateRangesFound": 3,
        "positions": [
          {
            "title": "Senior Backend Engineer",
            "start": "2022-02",
            "end": "present",
            "isCurrent": true,
            "months": 57,
            "skills": [
              "Anthropic API",
              "FastAPI",
              "Kubernetes",
              "LLMs"
            ]
          },
          {
            "title": "Backend Engineer",
            "start": "2019-09",
            "end": "2022-01",
            "isCurrent": false,
            "months": 29,
            "skills": [
              "CI/CD",
              "Celery",
              "Django",
              "Django REST Framework"
            ]
          },
          {
            "title": "Software Developer",
            "start": "2018-06",
            "end": "2019-08",
            "isCurrent": false,
            "months": 15,
            "skills": [
              "JavaScript",
              "Python",
              "SQL"
            ]
          }
        ]
      },
      "titles": [
        "Senior Backend Engineer",
        "Backend Engineer",
        "Software Developer"
      ],
      "currentTitle": "Senior Backend Engineer",
      "roleFamilies": [
        "backend"
      ],
      "seniority": "senior",
      "senioritySource": "title",
      "certifications": [],
      "warnings": []
    }
  },
  "message": null
}
```

### Errors

Same file again -> `409`

```json
{
  "success": false,
  "message": "This file was already uploaded as resume bbc2275e-4422-4eb3-924d-ea6cea28189b",
  "errors": [
    {
      "field": "file",
      "message": "duplicate of resume bbc2275e-4422-4eb3-924d-ea6cea28189b"
    }
  ],
  "traceId": "e2d1db66d97948d88ef42fa178078a27"
}
```

Unsupported type -> `415`

```json
{
  "success": false,
  "message": "Unsupported file extension '.exe'; allowed: .pdf, .docx, .txt",
  "errors": [],
  "traceId": "119543d1b8a14435bebdac8aaca4a879"
}
```

## Create a job

```bash
curl -s -X POST $API/api/jobs -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d @samples/jobs/ai_backend_engineer.json
```

`201 Created`

```json
{
  "success": true,
  "data": {
    "id": "e5253ea8-801c-4e40-9029-71c47db164d3",
    "title": "Senior AI Backend Engineer (Python/FastAPI)",
    "description": "We are building LLM-powered products for recruiting teams and need a senior backend engineer to own our Python services.\n\nResponsibilities:\n- Design and operate async REST APIs in FastAPI.\n- Build retrieval-augmented generation (RAG) pipelines on PostgreSQL with pgvector.\n- Integrate LLM providers (OpenAI API, Anthropic API) with retries, timeouts and cost controls.\n\nRequirements:\n- 5+ years of professional backend engineering experience.\n- Must have: Python and FastAPI.\n- Strong PostgreSQL and SQLAlchemy skills; Docker and CI/CD with GitHub Actions.\n- Experience with LLMs, embeddings and prompt engineering.\n- Testing discipline with pytest.\n\nNice to have:\n- Kubernetes, Terraform, Redis.\n- Experience with Kafka or other event streaming is a plus.",
    "ownerId": "4347d989-c395-4d8a-bc5f-66ed22bb6945",
    "createdAt": "2026-10-08T14:25:13.418375",
    "analysis": {
      "analyzerVersion": "1.0.0",
      "taxonomyVersion": "2026.10.2",
      "title": "Senior AI Backend Engineer (Python/FastAPI)",
      "seniority": "senior",
      "senioritySource": "title",
      "roleFamilies": [
        "backend",
        "ml_ai"
      ],
      "minYears": 5.0,
      "minYearsSource": "text",
      "requirements": [
        {
          "name": "Python",
          "category": "language",
          "importance": "critical",
          "source": "explicit",
          "inTaxonomy": true,
          "minYears": null,
          "mentions": 2
        },
        {
          "name": "FastAPI",
          "category": "backend",
          "importance": "critical",
          "source": "explicit",
          "inTaxonomy": true,
          "minYears": null,
          "mentions": 2
        },
        {
          "name": "LLMs",
          "category": "ml_ai",
          "importance": "required",
          "source": "cue",
          "inTaxonomy": true,
          "minYears": null,
          "mentions": 3
        },
        {
          "name": "REST APIs",
          "category": "architecture",
          "importance": "required",
          "source": "mentioned",
          "inTaxonomy": true,
          "minYears": null,
          "mentions": 1
        },
        {
          "name": "RAG",
          "category": "ml_ai",
          "importance": "required",
          "source": "mentioned",
          "inTaxonomy": true,
          "minYears": null,
          "mentions": 2
        },
        {
          "name": "PostgreSQL",
          "category": "database",
          "importance": "required",
          "source": "cue",
          "inTaxonomy": true,
          "minYears": null,
          "mentions": 2
        }
      ],
      "focusSkills": [
        "LLMs",
        "Python",
        "FastAPI",
        "RAG",
        "PostgreSQL"
      ],
      "unknownExplicitSkills": []
    }
  },
  "message": null
}
```

## Analyze a match

```bash
curl -s -X POST $API/api/matching/analyze -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"resumeId":"bbc2275e-4422-4eb3-924d-ea6cea28189b","jobId":"e5253ea8-801c-4e40-9029-71c47db164d3"}'
```

`201 Created` (the same call again returns `200` with the same `id` - idempotent per scoring version)

```json
{
  "success": true,
  "data": {
    "id": "ca9c30f2-7455-4f87-b91d-8b797098dab3",
    "resumeId": "bbc2275e-4422-4eb3-924d-ea6cea28189b",
    "jobId": "e5253ea8-801c-4e40-9029-71c47db164d3",
    "matchPercent": 89.3,
    "rawScore": 89.3,
    "verdict": "strong",
    "scoringVersion": "1.0.0+deeb6dad",
    "promptVersion": "match_explanation/v1",
    "breakdown": [
      {
        "key": "required_skills",
        "label": "Required skills",
        "score": 97.4,
        "weight": 0.4,
        "effectiveWeight": 0.4,
        "contribution": 38.95,
        "summary": "16/17 matched, 1 via related skills",
        "details": {
          "criticalWeight": 2.0
        }
      },
      {
        "key": "nice_to_have",
        "label": "Nice-to-have skills",
        "score": 50.0,
        "weight": 0.1,
        "effectiveWeight": 0.1,
        "contribution": 5.0,
        "summary": "2/4 matched",
        "details": {}
      },
      {
        "key": "experience",
        "label": "Experience",
        "score": 100.0,
        "weight": 0.2,
        "effectiveWeight": 0.2,
        "contribution": 20.0,
        "summary": "8.4 of 5+ years required",
        "details": {
          "ratio": 1.68
        }
      },
      {
        "key": "role",
        "label": "Role / title alignment",
        "score": 76.2,
        "weight": 0.1,
        "effectiveWeight": 0.1,
        "contribution": 7.62,
        "summary": "'Senior Backend Engineer' vs 'Senior AI Backend Engineer (Python/FastAPI)'",
        "details": {
          "titleSimilarity": 0.66,
          "seniorityFit": 1.0
        }
      },
      {
        "key": "semantic",
        "label": "Semantic similarity",
        "score": 88.8,
        "weight": 0.2,
        "effectiveWeight": 0.2,
        "contribution": 17.77,
        "summary": "best section: experience (raw cosine 0.4053)",
        "details": {
          "raw": 0.4053
        }
      }
    ],
    "knockouts": [],
    "skills": {
      "matchedRequired": [
        {
          "name": "Python",
          "category": "language",
          "importance": "critical",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 6.0,
          "lastUsed": "present",
          "requiredYears": null
        },
        {
          "name": "FastAPI",
          "category": "backend",
          "importance": "critical",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 4.8,
          "lastUsed": "present",
          "requiredYears": null
        },
        {
          "name": "LLMs",
          "category": "ml_ai",
          "importance": "required",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 4.8,
          "lastUsed": "present",
          "requiredYears": null
        },
        {
          "name": "REST APIs",
          "category": "architecture",
          "importance": "required",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 2.4,
          "lastUsed": "2022-01",
          "requiredYears": null
        },
        {
          "name": "RAG",
          "category": "ml_ai",
          "importance": "required",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 4.8,
          "lastUsed": "present",
          "requiredYears": null
        },
        {
          "name": "PostgreSQL",
          "category": "database",
          "importance": "required",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 7.2,
          "lastUsed": "present",
          "requiredYears": null
        }
      ],
      "missingRequired": [],
      "matchedNiceToHave": [
        {
          "name": "Kubernetes",
          "category": "devops",
          "importance": "nice_to_have",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 4.8,
          "lastUsed": "present",
          "requiredYears": null
        },
        {
          "name": "Redis",
          "category": "database",
          "importance": "nice_to_have",
          "matchType": "exact",
          "credit": 1.0,
          "via": [],
          "evidenced": true,
          "yearsUsed": 2.4,
          "lastUsed": "2022-01",
          "requiredYears": null
        }
      ],
      "missingNiceToHave": [
        {
          "name": "Terraform",
          "category": "devops",
          "importance": "nice_to_have",
          "matchType": "missing",
          "credit": 0.0,
          "via": [],
          "evidenced": false,
          "yearsUsed": null,
          "lastUsed": null,
          "requiredYears": null
        },
        {
          "name": "Kafka",
          "category": "data",
          "importance": "nice_to_have",
          "matchType": "missing",
          "credit": 0.0,
          "via": [],
          "evidenced": false,
          "yearsUsed": null,
          "lastUsed": null,
          "requiredYears": null
        }
      ]
    },
    "experience": {
      "candidateYears": 8.4,
      "requiredYears": 5.0,
      "ratio": 1.68,
      "source": "date_ranges",
      "positions": 3
    },
    "roleMatch": {
      "candidateTitle": "Senior Backend Engineer",
      "jobTitle": "Senior AI Backend Engineer (Python/FastAPI)",
      "titleSimilarity": 0.66,
      "candidateSeniority": "senior",
      "jobSeniority": "senior",
      "seniorityFit": 1.0,
      "candidateFamilies": [
        "backend"
      ],
      "jobFamilies": [
        "backend",
        "ml_ai"
      ]
    },
    "semantic": {
      "provider": "hashing",
      "sectionSimilarity": {
        "education": -0.0104,
        "experience": 0.4579,
        "skills": 0.4167,
        "summary": 0.2661
      },
      "bestSection": "experience",
      "raw": 0.4053,
      "floor": 0.05,
      "ceiling": 0.45
    },
    "recommendedImprovements": [
      {
        "code": "transferable_skill",
        "priority": "medium",
        "message": "Embeddings is required; the resume shows the related RAG. Describe comparable work to make the transfer to Embeddings explicit.",
        "skills": [
          "Embeddings",
          "RAG"
        ]
      },
      {
        "code": "add_evidence",
        "priority": "medium",
        "message": "Prompt Engineering appear only in a skills list. Add experience or project bullets that show how they were used.",
        "skills": [
          "Prompt Engineering"
        ]
      },
      {
        "code": "nice_to_have",
        "priority": "low",
        "message": "Nice-to-have skills that would strengthen the match: Terraform, Kafka.",
        "skills": [
          "Terraform",
          "Kafka"
        ]
      }
    ],
    "interviewPrepTopics": [
      {
        "topic": "Python in production",
        "reason": "Evidenced in the experience section; probe depth, trade-offs and ownership.",
        "skills": [
          "Python"
        ]
      },
      {
        "topic": "FastAPI in production",
        "reason": "Evidenced in the experience section; probe depth, trade-offs and ownership.",
        "skills": [
          "FastAPI"
        ]
      },
      {
        "topic": "PostgreSQL in production",
        "reason": "Evidenced in the experience section; probe depth, trade-offs and ownership.",
        "skills": [
          "PostgreSQL"
        ]
      },
      {
        "topic": "Transfer from RAG to Embeddings",
        "reason": "Only the related skill RAG was found; assess how quickly it transfers.",
        "skills": [
          "Embeddings",
          "RAG"
        ]
      },
      {
        "topic": "Hands-on usage of listed skills",
        "reason": "Listed without supporting experience bullets.",
        "skills": [
          "Prompt Engineering"
        ]
      }
    ],
    "explanation": {
      "summary": "Scored 89.3/100 for 'Senior AI Backend Engineer (Python/FastAPI)': a strong match. The resume covers 16 of 17 required skills, with partial credit for 1 via related skills. Dated experience totals 8.4 years against 5+ required.",
      "strengths": [
        "Required skills present: Python, FastAPI, LLMs, REST APIs, RAG and 11 more.",
        "Nice-to-have skills present: Kubernetes and Redis.",
        "Meets the stated experience requirement.",
        "Strongest component: Experience (100/100)."
      ],
      "gaps": [
        "Embeddings only indirectly covered by RAG.",
        "Missing nice-to-haves: Terraform and Kafka."
      ],
      "source": "offline_template",
      "provider": "offline",
      "model": "offline-template-v1",
      "promptVersion": "match_explanation/v1"
    },
    "createdAt": "2026-10-08T14:25:13.469533",
    "updatedAt": "2026-10-08T14:25:13.468317"
  },
  "message": null
}
```

### Knock-out example (.NET resume vs the Python JD)

Abbreviated to the fields that show the cap:

```json
{
  "matchPercent": 40.0,
  "rawScore": 49.3,
  "knockouts": [
    {
      "code": "missing_critical_skill",
      "message": "Missing must-have skill(s): Python, FastAPI",
      "cap": 40.0,
      "skills": [
        "Python",
        "FastAPI"
      ]
    }
  ],
  "missingRequired": [
    "Python",
    "FastAPI",
    "LLMs",
    "RAG",
    "pgvector",
    "OpenAI API",
    "Anthropic API",
    "SQLAlchemy",
    "Git",
    "Embeddings",
    "Prompt Engineering"
  ],
  "explanation": {
    "summary": "Scored 40/100 for 'Senior AI Backend Engineer (Python/FastAPI)': a weak match. The resume covers 3 of 17 required skills, with partial credit for 3 via related skills. Dated experience totals 9.3 years against 5+ required. Score capped: Missing must-have skill(s): Python, FastAPI.",
    "strengths": [
      "Required skills present: REST APIs, Docker and CI/CD.",
      "Nice-to-have skills present: Kubernetes, Redis and Kafka.",
      "Meets the stated experience requirement.",
      "Strongest component: Experience (100/100)."
    ],
    "gaps": [
      "Missing must-have skills: Python and FastAPI.",
      "Missing required skills: LLMs, RAG, pgvector, OpenAI API, Anthropic API and 4 more.",
      "PostgreSQL only indirectly covered by SQL and SQL Server.",
      "GitHub Actions only indirectly covered by Azure DevOps and CI/CD.",
      "Missing nice-to-haves: Terraform."
    ],
    "source": "template_fallback",
    "provider": "template",
    "model": "offline-template-v1",
    "promptVersion": "match_explanation/v1"
  }
}
```

## Get a stored match

```bash
curl -s $API/api/matching/ca9c30f2-7455-4f87-b91d-8b797098dab3 -H "Authorization: Bearer $TOKEN"
```

`200 OK` - same payload as above.

## Rank candidates for a job

```bash
curl -s "$API/api/candidates/ranking?job_id=7f61f83d-7094-476b-bcfd-a0dc43fd07db&page=1&pageSize=5" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "success": true,
  "data": {
    "jobId": "7f61f83d-7094-476b-bcfd-a0dc43fd07db",
    "scoringVersion": "1.0.0+deeb6dad",
    "candidatesConsidered": 5,
    "newlyComputed": 5,
    "items": [
      {
        "rank": 1,
        "resumeId": "8dca6367-266a-466b-b415-4f020cd4e10b",
        "matchId": "1ab72758-4552-4f3f-8535-4ef2a61930fa",
        "filename": "rohan_deshpande_dotnet_backend.pdf",
        "currentTitle": "Senior Software Engineer",
        "matchPercent": 96.0,
        "verdict": "strong",
        "requiredCoverage": 93.3,
        "knockouts": [],
        "topReasons": [
          "Matches 11/13 required skills",
          "9.3 years experience vs 4+ required",
          "Title 'Senior .NET Backend Developer' (100% title match)"
        ]
      },
      {
        "rank": 2,
        "resumeId": "01945844-66a8-48bd-a0b0-4491b14349f2",
        "matchId": "78762d13-f79a-45e1-8e80-13fe408d47ac",
        "filename": "sofia_alvarez_data_engineer.txt",
        "currentTitle": "Senior Data Engineer",
        "matchPercent": 40.0,
        "verdict": "weak",
        "requiredCoverage": 26.7,
        "knockouts": [
          "missing_critical_skill"
        ],
        "topReasons": [
          "Missing must-have skill(s): C#, .NET",
          "Matches 3/13 required skills",
          "8.3 years experience vs 4+ required"
        ]
      },
      {
        "rank": 3,
        "resumeId": "bbc2275e-4422-4eb3-924d-ea6cea28189b",
        "matchId": "dffdef59-2748-4669-83c7-b5292edba320",
        "filename": "daniel_okafor_ai_backend.txt",
        "currentTitle": "Senior Backend Engineer",
        "matchPercent": 40.0,
        "verdict": "weak",
        "requiredCoverage": 23.3,
        "knockouts": [
          "missing_critical_skill"
        ],
        "topReasons": [
          "Missing must-have skill(s): C#, .NET",
          "Matches 1/13 required skills",
          "8.4 years experience vs 4+ required"
        ]
      },
      {
        "rank": 4,
        "resumeId": "da39c002-bf5b-46d7-982e-62f7111d68b3",
        "matchId": "6739f433-c6ba-4c95-8ce6-9a1f924f9cbe",
        "filename": "maya_chen_ml_engineer.docx",
        "currentTitle": "Machine Learning Engineer",
        "matchPercent": 40.0,
        "verdict": "weak",
        "requiredCoverage": 20.0,
        "knockouts": [
          "missing_critical_skill"
        ],
        "topReasons": [
          "Missing must-have skill(s): C#, .NET",
          "Matches 1/13 required skills",
          "6.4 years experience vs 4+ required"
        ]
      },
      {
        "rank": 5,
        "resumeId": "66f20ca4-54da-45ae-9fd7-36c277a20b76",
        "matchId": "a424f4b8-2d1b-432f-846d-a31b0e8ea560",
        "filename": "jordan_lee_junior_web.txt",
        "currentTitle": "Web Developer",
        "matchPercent": 26.6,
        "verdict": "weak",
        "requiredCoverage": 10.0,
        "knockouts": [
          "missing_critical_skill"
        ],
        "topReasons": [
          "Missing must-have skill(s): C#, .NET",
          "Matches 1/13 required skills",
          "2.2 years experience vs 4+ required"
        ]
      }
    ],
    "page": 1,
    "pageSize": 5,
    "totalCount": 5,
    "totalPages": 1
  },
  "message": null
}
```

## List resumes (paginated)

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "8dca6367-266a-466b-b415-4f020cd4e10b",
        "filename": "rohan_deshpande_dotnet_backend.pdf",
        "fileType": "pdf",
        "createdAt": "2026-10-08T14:25:13.356687",
        "currentTitle": "Senior Software Engineer",
        "seniority": "senior",
        "totalYears": 9.3,
        "topSkills": [
          "Azure",
          "SQL",
          "ASP.NET Core"
        ]
      },
      {
        "id": "da39c002-bf5b-46d7-982e-62f7111d68b3",
        "filename": "maya_chen_ml_engineer.docx",
        "fileType": "docx",
        "createdAt": "2026-10-08T14:25:13.196748",
        "currentTitle": "Machine Learning Engineer",
        "seniority": "senior",
        "totalYears": 6.4,
        "topSkills": [
          "Machine Learning",
          "NLP",
          "PyTorch"
        ]
      }
    ],
    "page": 1,
    "pageSize": 2,
    "totalCount": 5,
    "totalPages": 3
  },
  "message": null
}
```

## Error envelope

No token -> `401`

```json
{
  "success": false,
  "message": "Not authenticated",
  "errors": [],
  "traceId": "01f3bb44a5054be2a1b77af9003a6ac8"
}
```

Validation -> `422`

```json
{
  "success": false,
  "message": "Validation failed",
  "errors": [
    {
      "field": "title",
      "message": "String should have at least 3 characters"
    },
    {
      "field": "description",
      "message": "Field required"
    }
  ],
  "traceId": "d663f48e06eb42d0a6415852776e584d"
}
```

## Health

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "taxonomy": "ok (194 skills)"
  }
}
```
