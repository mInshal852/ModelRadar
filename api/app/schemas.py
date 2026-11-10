"""Stable, read-only response schemas of the public API."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel

AnnouncementKind = Literal["model_release", "update", "deprecation", "research", "other"]
DatePrecision = Literal["day", "datetime"]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class CompanyRef(BaseModel):
    slug: str
    name: str


class CategoryRef(BaseModel):
    slug: str
    name: str


class Announcement(BaseModel):
    id: int
    title: str  # exactly as published
    description: str | None  # the source's own text, or null
    kind: AnnouncementKind
    published_at: dt.datetime | None  # original publication date (UTC), or null
    published_precision: DatePrecision | None
    original_url: str
    source_domain: str
    source_name: str
    company: CompanyRef
    categories: list[CategoryRef]  # announcement categories, else the company's categories
    models: list[str]  # only detected model versions (none until model detection exists)


class Category(BaseModel):
    slug: str
    name: str
    description: str | None
    announcement_count: int
    company_count: int
    children: list["Category"] = []


class Company(BaseModel):
    slug: str
    name: str
    website_url: str
    country: str | None
    description: str | None
    categories: list[CategoryRef]
    announcement_count: int
    source_count: int
    latest_published_at: dt.datetime | None


class ModelVersion(BaseModel):
    display_name: str
    version_label: str | None
    first_announced_at: dt.datetime | None
    first_announced_precision: DatePrecision | None
    announcement_title: str
    announcement_url: str
    categories: list[CategoryRef]


class ModelFamily(BaseModel):
    slug: str
    family_name: str
    company: CompanyRef
    versions: list[ModelVersion]


class SourceRun(BaseModel):
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    http_status: int | None
    items_found: int
    items_new: int
    items_filtered: int


class Source(BaseModel):
    id: int
    name: str
    company: CompanyRef
    kind: str
    url: str
    hosting: str
    hosting_notes: str | None
    content_scope: str
    verification_level: str
    verified_at: dt.datetime | None
    verification_notes: str | None
    poll_interval_minutes: int
    enabled: bool
    status: str | None  # null = never synchronised
    consecutive_failures: int
    last_synced_at: dt.datetime | None
    last_error: str | None
    announcement_count: int
    last_run: SourceRun | None


class Meta(BaseModel):
    announcement_count: int
    company_count: int
    source_count: int
    enabled_source_count: int
    last_synced_at: dt.datetime | None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, str]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
