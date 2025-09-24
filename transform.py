from datetime import date, timedelta
from typing import List, Optional, Tuple
import pandas as pd
from models import JiraIssue, AppConfig, ComputeResults, DailyPoint


class DataTransformer:
    """Transforms and filters Jira data for scope/completed analysis."""
    
    def apply_filters(self, issues: List[JiraIssue], config: AppConfig) -> Tuple[List[JiraIssue], int]:
        """Apply all configured filters to issues and return filtered list + exclusion count."""
        excluded_count = 0
        filtered_issues = []
        
        for issue in issues:
            # Track if issue should be excluded
            exclude = False
            
            # Exclude zombie resolution
            if config.exclude_zombie and issue.resolution and "zombie" in issue.resolution.lower():
                exclude = True
            
            # Drop missing created
            if config.drop_missing_created and issue.created_day is None:
                exclude = True
            
            # Drop missing done transition
            if config.drop_missing_done and issue.done_day is None:
                exclude = True
            
            # Exclude specific keys
            if issue.key in config.exclude_keys:
                exclude = True
            
            # Filter by labels
            if config.labels_filter and not any(label in config.labels_filter for label in issue.labels):
                exclude = True
            
            # Filter by components
            if config.components_filter and not any(comp in config.components_filter for comp in issue.components):
                exclude = True
            
            # Filter by epics
            if config.epics_filter and issue.epic not in config.epics_filter:
                exclude = True
            
            # Filter by assignees
            if config.assignees_filter and issue.assignee not in config.assignees_filter:
                exclude = True
            
            # Include/exclude subtasks based on issue type
            if not config.include_subtasks and issue.issue_type and "sub" in issue.issue_type.lower():
                exclude = True
            
            if exclude:
                excluded_count += 1
            else:
                filtered_issues.append(issue)
        
        return filtered_issues, excluded_count
    
    def determine_time_domain(self, issues: List[JiraIssue], config: AppConfig) -> Tuple[date, date, List[str]]:
        """Determine t0 and t1 for the analysis domain."""
        warnings = []
        
        # Determine t0 (start date)
        if config.t0_override:
            t0 = config.t0_override
        else:
            created_dates = [issue.created_day for issue in issues if issue.created_day]
            if not created_dates:
                t0 = date(2025, 9, 9)  # Default September 9th
                warnings.append("No created dates found, using default start date")
            else:
                t0 = min(created_dates)
        
        # Determine t1 (end date)
        if config.t1_override:
            t1 = config.t1_override
        else:
            # Try to use due dates first
            due_dates = [issue.due_day for issue in issues if issue.due_day]
            
            if due_dates:
                t1 = max(due_dates)
            else:
                # Use fallback logic
                warnings.append(f"No due dates found, using fallback: {config.t1_fallback}")
                
                if config.t1_fallback == "Max Done":
                    done_dates = [issue.done_day for issue in issues if issue.done_day]
                    if done_dates:
                        t1 = max(done_dates)
                    else:
                        t1 = date.today()
                        warnings.append("No done dates found either, using today")
                elif config.t1_fallback == "Max Created":
                    created_dates = [issue.created_day for issue in issues if issue.created_day]
                    if created_dates:
                        t1 = max(created_dates)
                    else:
                        t1 = date.today()
                        warnings.append("No created dates found, using today")
                else:  # "Today"
                    t1 = date.today()
        
        # Ensure t1 >= t0
        if t1 < t0:
            t1 = t0
            warnings.append("t1 was before t0, adjusted t1 to equal t0")
        
        return t0, t1, warnings
    
    def compute_daily_series(self, issues: List[JiraIssue], t0: date, t1: date, config: AppConfig) -> List[DailyPoint]:
        """Compute daily scope and completed series."""
        # Create continuous date range
        date_range = []
        current_date = t0
        while current_date <= t1:
            date_range.append(current_date)
            current_date += timedelta(days=1)
        
        daily_points = []
        prev_scope = 0.0
        prev_completed = 0.0
        
        for current_date in date_range:
            # Calculate scope: sum of story points for ALL issues created <= current_date
            # (Don't filter by t0 - include all historical tickets in scope)
            scope = 0.0
            for issue in issues:
                if issue.created_day and issue.created_day <= current_date:
                    scope += issue.story_points
                    
                    # Subtract if removed from scope and subtraction is enabled
                    if (config.subtract_removed and 
                        issue.removed_day and 
                        issue.removed_day <= current_date):
                        scope -= issue.story_points
            
            # Calculate completed: sum of story points for issues completed >= t0 and <= current_date
            # Only count completion work from t0 forward, but include any ticket (regardless of creation date)
            # Use actual transition dates for accurate tracking
            completed = 0.0
            for issue in issues:
                completion_date = None
                
                # Strategy: Find the earliest completion date from multiple workflow paths
                completion_candidates = []
                
                # Option 1: Specific target_status transition (e.g., "Done Dev")
                if (config.target_status and 
                    config.target_status in issue.target_status_transitions):
                    target_date = issue.target_status_transitions[config.target_status]
                    if target_date:
                        completion_candidates.append(target_date)
                
                # Option 2: Any configured done_statuses transitions
                if config.done_statuses:
                    for done_status in config.done_statuses:
                        if done_status in issue.target_status_transitions:
                            transition_date = issue.target_status_transitions[done_status]
                            if transition_date:
                                completion_candidates.append(transition_date)
                
                # Option 3: Generic done_day fallback
                if issue.done_day:
                    completion_candidates.append(issue.done_day)
                
                # Option 4: Common completion statuses (broader fallback for different workflows)
                common_completion_statuses = ["Done", "Closed", "Resolved", "Complete", "Completed"]
                for status in common_completion_statuses:
                    if status in issue.target_status_transitions:
                        transition_date = issue.target_status_transitions[status]
                        if transition_date:
                            completion_candidates.append(transition_date)
                
                # Use the earliest completion date found
                if completion_candidates:
                    completion_date = min(completion_candidates)
                
                # Only count if completed within time window and in scope by current_date
                if (completion_date and 
                    completion_date >= t0 and 
                    completion_date <= current_date and
                    issue.created_day and 
                    issue.created_day <= current_date):
                    completed += issue.story_points
            
            # Calculate deltas
            delta_scope = scope - prev_scope
            delta_completed = completed - prev_completed
            
            daily_points.append(DailyPoint(
                date=current_date,
                scope=scope,
                completed=completed,
                delta_scope=delta_scope,
                delta_completed=delta_completed
            ))
            
            prev_scope = scope
            prev_completed = completed
        
        return daily_points
    
    def compute_results(self, issues: List[JiraIssue], config: AppConfig) -> ComputeResults:
        """Compute complete analysis results."""
        # Apply filters
        filtered_issues, excluded_count = self.apply_filters(issues, config)
        
        # Determine time domain
        t0, t1, warnings = self.determine_time_domain(filtered_issues, config)
        
        # Compute daily series
        daily_series = self.compute_daily_series(filtered_issues, t0, t1, config)
        
        # Calculate final metrics
        max_scope = daily_series[-1].scope if daily_series else 0.0
        completed_at_t1 = daily_series[-1].completed if daily_series else 0.0
        percent_complete = (completed_at_t1 / max_scope * 100) if max_scope > 0 else 0.0
        
        return ComputeResults(
            t0=t0,
            t1=t1,
            max_scope=max_scope,
            completed_at_t1=completed_at_t1,
            percent_complete=percent_complete,
            included_issues_count=len(filtered_issues),
            excluded_issues_count=excluded_count,
            daily_series=daily_series,
            warnings=warnings
        )
    
    def issues_to_dataframe(self, issues: List[JiraIssue]) -> pd.DataFrame:
        """Convert issues list to DataFrame for display."""
        data = []
        for issue in issues:
            data.append({
                "key": issue.key,
                "summary": issue.summary,
                "story_points": round(issue.story_points, 1),
                "created_day": issue.created_day.strftime("%Y-%m-%d") if issue.created_day else "",
                "done_day": issue.done_day.strftime("%Y-%m-%d") if issue.done_day else "",
                "due_day": issue.due_day.strftime("%Y-%m-%d") if issue.due_day else "",
                "resolution": issue.resolution,
                "labels": ", ".join(issue.labels),
                "components": ", ".join(issue.components),
                "epic": issue.epic,
                "assignee": issue.assignee
            })
        
        return pd.DataFrame(data)
    
    def daily_series_to_dataframe(self, daily_series: List[DailyPoint]) -> pd.DataFrame:
        """Convert daily series to DataFrame."""
        data = []
        for point in daily_series:
            data.append({
                "date": point.date.strftime("%Y-%m-%d"),
                "scope": round(point.scope, 1),
                "completed": round(point.completed, 1),
                "delta_scope": round(point.delta_scope, 1),
                "delta_completed": round(point.delta_completed, 1)
            })
        
        return pd.DataFrame(data)
    
    def generate_weekly_status_table(self, issues: List[JiraIssue], t0: date, t1: date, config: AppConfig) -> pd.DataFrame:
        """Generate weekly status breakdown table respecting start date filtering."""
        from datetime import timedelta
        import math
        
        # Define status categories
        done_statuses = {"Done", "Closed", "Resolved"}
        in_flight_statuses = {"In Analysis", "Done Analysis", "Done Dev", "In Test", "Done Test", "Ready to Deploy", "In Dev", "To Review"}
        not_started_statuses = {"To Do", "Ready For Development", "Ready for grooming", "Ready for Grooming"}
        blocked_statuses = {"Blocked", "On Hold"}
        
        # Calculate total weeks from t0 to t1
        total_days = (t1 - t0).days
        total_weeks = math.ceil(total_days / 7)
        
        weekly_data = []
        
        for week_num in range(1, total_weeks + 1):
            week_start = t0 + timedelta(days=(week_num - 1) * 7)
            week_end = min(week_start + timedelta(days=6), t1)
            
            # Calculate scope: issues created by week_end (like daily series)
            total_sp = sum(
                issue.story_points 
                for issue in issues 
                if issue.created_day and issue.created_day <= week_end
            )
            
            # Calculate done: issues completed by week_end but after t0 (respecting baseline)
            done_sp = 0.0
            for issue in issues:
                if not (issue.created_day and issue.created_day <= week_end):
                    continue
                    
                completion_date = None
                
                # Use same improved logic as daily series for completion detection
                completion_candidates = []
                
                # Option 1: Specific target_status transition (e.g., "Done Dev")
                if (config.target_status and 
                    config.target_status in issue.target_status_transitions):
                    target_date = issue.target_status_transitions[config.target_status]
                    if target_date:
                        completion_candidates.append(target_date)
                
                # Option 2: Any configured done_statuses transitions
                if config.done_statuses:
                    for done_status in config.done_statuses:
                        if done_status in issue.target_status_transitions:
                            transition_date = issue.target_status_transitions[done_status]
                            if transition_date:
                                completion_candidates.append(transition_date)
                
                # Option 3: Generic done_day fallback
                if issue.done_day:
                    completion_candidates.append(issue.done_day)
                
                # Option 4: Common completion statuses (broader fallback for different workflows)
                common_completion_statuses = ["Done", "Closed", "Resolved", "Complete", "Completed"]
                for status in common_completion_statuses:
                    if status in issue.target_status_transitions:
                        transition_date = issue.target_status_transitions[status]
                        if transition_date:
                            completion_candidates.append(transition_date)
                
                # Use the earliest completion date found
                if completion_candidates:
                    completion_date = min(completion_candidates)
                
                # Count as done if completed within time window and after t0
                if (completion_date and 
                    completion_date >= t0 and 
                    completion_date <= week_end):
                    done_sp += issue.story_points
            
            # Calculate work in progress: total scope minus done (remaining work)
            # Note: This shows remaining work as of week_end, not historical status breakdown
            remaining_sp = total_sp - done_sp
            
            # For now, we can only accurately show Done vs Remaining
            # Historical status breakdown would require full changelog analysis
            in_flight_sp = remaining_sp  # All remaining work considered "in flight"
            not_started_sp = 0.0  # Cannot accurately determine historical "not started" 
            blocked_sp = 0.0  # Cannot accurately determine historical "blocked"
            
            # Calculate target by due dates: issues that should be done by week_end based on due dates
            # Only count issues due within our analysis window (>= t0)
            target_by_due_sp = sum(
                issue.story_points 
                for issue in issues 
                if (issue.created_day and issue.created_day <= week_end and
                    issue.due_day and issue.due_day >= t0 and issue.due_day <= week_end)
            )
            
            # Calculate percentage done
            percent_done = (done_sp / total_sp * 100) if total_sp > 0 else 0
            
            weekly_data.append({
                "Week #": week_num,
                "Week End Date": week_end.strftime("%Y-%m-%d"),
                "Total SP": round(total_sp, 1),
                "Done": round(done_sp, 1),
                "Target by Due Date": round(target_by_due_sp, 1),
                "In Flight": round(in_flight_sp, 1),
                "Not Started": round(not_started_sp, 1),
                "Blocked": round(blocked_sp, 1),
                "% Done": round(percent_done, 1)
            })
        
        return pd.DataFrame(weekly_data)


# Singleton instance
data_transformer = DataTransformer()
