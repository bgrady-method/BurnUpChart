import os
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class JiraIssue(BaseModel):
    """Normalized Jira issue model."""
    key: str
    summary: Optional[str] = ""
    story_points: float = 0.0
    created_day: Optional[date] = None
    done_day: Optional[date] = None
    due_day: Optional[date] = None
    resolution: Optional[str] = ""
    labels: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    epic: Optional[str] = ""
    assignee: Optional[str] = ""
    status: Optional[str] = ""
    issue_type: Optional[str] = ""
    removed_day: Optional[date] = None  # When removed from scope
    target_status_transitions: Dict[str, Optional[date]] = Field(default_factory=dict)  # Status -> first transition date


class DailyPoint(BaseModel):
    """Daily scope/completed data point."""
    date: date
    scope: float
    completed: float
    delta_scope: float = 0.0
    delta_completed: float = 0.0


class AppConfig(BaseModel):
    """Application configuration state."""
    jql: str = '"Epic Link" = PL-54667'
    timezone: str = "America/Toronto"
    cache_raw: bool = True
    
    # Domain settings
    t0_override: Optional[date] = date(2025, 9, 9)  # September 9th
    t1_override: Optional[date] = date(2025, 11, 11)  # November 11th
    t1_fallback: str = "Max Done"  # Options: "Max Done", "Max Created", "Today"
    target_status: str = "Done"  # Target status to track completion
    done_statuses: List[str] = Field(default_factory=list)
    removed_statuses: List[str] = Field(default_factory=list)
    subtract_removed: bool = False
    
    # Filters
    exclude_zombie: bool = True
    drop_missing_created: bool = False
    drop_missing_done: bool = False
    exclude_keys: List[str] = Field(default_factory=lambda: ["PL-56887", "PL-56143", "PL-56886"])
    labels_filter: List[str] = Field(default_factory=list)
    components_filter: List[str] = Field(default_factory=list)
    epics_filter: List[str] = Field(default_factory=list)
    assignees_filter: List[str] = Field(default_factory=list)
    include_subtasks: bool = True
    
    # UI settings
    show_intermediate: bool = False
    show_validation: bool = False


class ComputeResults(BaseModel):
    """Results of scope/completed computation."""
    t0: date
    t1: date
    max_scope: float
    completed_at_t1: float
    percent_complete: float
    included_issues_count: int
    excluded_issues_count: int
    daily_series: List[DailyPoint]
    warnings: List[str] = Field(default_factory=list)


class FieldCatalogs(BaseModel):
    """Catalogs of available field values for filtering."""
    statuses: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    epics: List[str] = Field(default_factory=list)
    assignees: List[str] = Field(default_factory=list)
    resolutions: List[str] = Field(default_factory=list)
