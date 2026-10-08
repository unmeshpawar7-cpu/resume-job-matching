"""ORM row -> response DTO mapping."""

from __future__ import annotations

from resume_matching.db.models import Job, MatchResult, Resume
from resume_matching.domain.job_analysis import JobAnalysis
from resume_matching.domain.profile import ResumeProfile
from resume_matching.domain.ranking import RankEntry, top_reasons
from resume_matching.domain.scoring import MatchComputation
from resume_matching.schemas.jobs import JobOut, JobSummary
from resume_matching.schemas.matching import (
    ExplanationOut,
    MatchOut,
    RankingItem,
    SkillBreakdown,
)
from resume_matching.schemas.resumes import ResumeOut, ResumeSummary


def resume_out(r: Resume) -> ResumeOut:
    return ResumeOut(
        id=r.id,
        filename=r.filename,
        file_type=r.file_type,
        content_type=r.content_type,
        size_bytes=r.size_bytes,
        page_count=r.page_count,
        checksum=r.checksum,
        owner_id=r.owner_id,
        embedding_model=r.embedding_model,
        created_at=r.created_at,
        profile=ResumeProfile.model_validate(r.profile),
    )


def resume_summary(r: Resume) -> ResumeSummary:
    p = ResumeProfile.model_validate(r.profile)
    return ResumeSummary(
        id=r.id,
        filename=r.filename,
        file_type=r.file_type,
        created_at=r.created_at,
        current_title=p.current_title,
        seniority=p.seniority,
        total_years=p.experience.total_years,
        top_skills=[s.name for s in p.skills[:8]],
    )


def job_out(j: Job) -> JobOut:
    return JobOut(
        id=j.id,
        title=j.title,
        description=j.description,
        owner_id=j.owner_id,
        created_at=j.created_at,
        analysis=JobAnalysis.model_validate(j.analysis),
    )


def job_summary(j: Job) -> JobSummary:
    a = JobAnalysis.model_validate(j.analysis)
    return JobSummary(
        id=j.id,
        title=j.title,
        created_at=j.created_at,
        seniority=a.seniority,
        min_years=a.min_years,
        required_skills=[r.name for r in a.required],
        nice_to_have_skills=[r.name for r in a.nice_to_have],
    )


def match_out(m: MatchResult) -> MatchOut:
    c = MatchComputation.model_validate(m.result)
    e = m.explanation
    return MatchOut(
        id=m.id,
        resume_id=m.resume_id,
        job_id=m.job_id,
        match_percent=c.overall_score,
        raw_score=c.raw_score,
        verdict=c.verdict,
        scoring_version=m.scoring_version,
        prompt_version=m.prompt_version,
        breakdown=c.components,
        knockouts=c.knockouts,
        skills=SkillBreakdown(
            matched_required=[s for s in c.required_skills if s.matched],
            missing_required=[s for s in c.required_skills if not s.matched],
            matched_nice_to_have=[s for s in c.nice_to_have_skills if s.matched],
            missing_nice_to_have=[s for s in c.nice_to_have_skills if not s.matched],
        ),
        experience=c.experience,
        role_match=c.role,
        semantic=c.semantic,
        recommended_improvements=c.recommendations,
        interview_prep_topics=c.interview_topics,
        explanation=ExplanationOut(
            summary=e["summary"],
            strengths=e.get("strengths", []),
            gaps=e.get("gaps", []),
            source=m.explanation_source,
            provider=m.llm_provider,
            model=m.llm_model,
            prompt_version=m.prompt_version,
        ),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def ranking_item(rank: int, entry: RankEntry, match: MatchResult, resume: Resume) -> RankingItem:
    c = entry.computation
    required = next((x.score for x in c.components if x.key == "required_skills"), None)
    profile = ResumeProfile.model_validate(resume.profile)
    return RankingItem(
        rank=rank,
        resume_id=resume.id,
        match_id=match.id,
        filename=resume.filename,
        current_title=profile.current_title,
        match_percent=c.overall_score,
        verdict=c.verdict,
        required_coverage=required,
        knockouts=[k.code for k in c.knockouts],
        top_reasons=top_reasons(c),
    )
