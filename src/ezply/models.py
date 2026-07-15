from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
    JSON,
    func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ats_type: Mapped[str] = mapped_column(String(50), nullable=False) # greenhouse, lever, ashby, smartrecruiters
    ats_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    raw_jobs = relationship("RawJob", back_populates="company")


class RawJob(Base):
    __tablename__ = "raw_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description_raw: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    job_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    company = relationship("Company", back_populates="raw_jobs")
    scored_job = relationship("ScoredJob", back_populates="raw_job", uselist=False)
    application = relationship("Application", back_populates="raw_job", uselist=False)


class ScoredJob(Base):
    __tablename__ = "scored_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_job_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_jobs.id"), nullable=False)
    embedding_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_requirements: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    concerns: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    raw_job = relationship("RawJob", back_populates="scored_job")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_job_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_jobs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="not_applied") # not_applied, applied, rejected, interview, offer
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    raw_job = relationship("RawJob", back_populates="application")


class ResumeProfile(Base):
    __tablename__ = "resume_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
