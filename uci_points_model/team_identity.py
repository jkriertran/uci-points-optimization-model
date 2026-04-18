from __future__ import annotations


def canonicalize_team_slug(team_slug: str, planning_year: int) -> str:
    cleaned = str(team_slug or "").strip()
    suffix = f"-{int(planning_year)}"
    if cleaned.endswith(suffix):
        return cleaned[: -len(suffix)]
    return cleaned


def build_team_artifact_stem(team_slug: str, planning_year: int) -> str:
    stable_slug = canonicalize_team_slug(team_slug, planning_year)
    return f"{stable_slug.replace('-', '_')}_{int(planning_year)}"
