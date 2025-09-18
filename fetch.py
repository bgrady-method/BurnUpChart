import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import streamlit as st
from dateutil.parser import parse as parse_date
from models import JiraIssue, FieldCatalogs


class JiraFetcher:
    """Fetches and processes Jira data via MCP server."""
    
    def __init__(self):
        self.mcp_server_name = "github.com/pashpashpash/mcp-atlassian"
    
    def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call MCP tool and return parsed response."""
        try:
            # This will be replaced with actual MCP call in the Streamlit app
            # For now, return mock data structure
            if "mcp_call_function" in st.session_state:
                result = st.session_state.mcp_call_function(
                    self.mcp_server_name, tool_name, arguments
                )
                
                # Parse JSON response if string
                if isinstance(result, str):
                    return json.loads(result)
                return result
            else:
                raise Exception("MCP interface not initialized")
            
        except Exception as e:
            st.error(f"MCP tool call failed ({tool_name}): {str(e)}")
            raise
    
    def search_issues(self, jql: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Search for issues using JQL."""
        try:
            all_issues = []
            start = 0
            batch_size = min(50, limit)  # MCP server limit is 50
            
            while len(all_issues) < limit:
                remaining = limit - len(all_issues)
                current_batch_size = min(batch_size, remaining)
                
                # Modify JQL to include pagination
                paginated_jql = f"({jql}) ORDER BY created ASC"
                
                result = self._call_mcp_tool("jira_search", {
                    "jql": paginated_jql,
                    "fields": "*all",
                    "limit": current_batch_size
                })
                
                if not result or not isinstance(result, list):
                    break
                
                batch_issues = result
                if not batch_issues:
                    break
                
                all_issues.extend(batch_issues)
                
                # If we got fewer than requested, we've reached the end
                if len(batch_issues) < current_batch_size:
                    break
                
                start += current_batch_size
            
            return all_issues[:limit]
            
        except Exception as e:
            st.error(f"Failed to search issues: {str(e)}")
            return []
    
    def get_issue_details(self, issue_key: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific issue."""
        try:
            result = self._call_mcp_tool("jira_get_issue", {
                "issue_key": issue_key,
                "expand": "changelog"
            })
            return result
        except Exception as e:
            st.warning(f"Failed to get details for {issue_key}: {str(e)}")
            return None
    
    def normalize_issue(self, raw_issue: Dict[str, Any], timezone: str = "America/Toronto") -> Optional[JiraIssue]:
        """Convert raw Jira issue data to normalized JiraIssue model."""
        try:
            # Extract basic fields
            key = raw_issue.get("key", "")
            if not key:
                return None
            
            metadata = raw_issue.get("metadata", {})
            
            # Extract fields from either search result format or detailed format
            title = metadata.get("title", "") or raw_issue.get("summary", "")
            story_points = self._extract_story_points(raw_issue)
            
            # Parse dates - handle both string and direct date formats
            created_day = self._parse_date_field(metadata.get("created_date") or raw_issue.get("created"))
            due_day = self._parse_date_field(raw_issue.get("due"))
            done_day = self._parse_date_field(raw_issue.get("done_day"))
            
            # Extract other fields
            resolution = raw_issue.get("resolution", "")
            status = raw_issue.get("status", "")
            issue_type = raw_issue.get("type", "")
            
            # Extract lists
            labels = self._extract_list_field(raw_issue.get("labels", []))
            components = self._extract_list_field(raw_issue.get("components", []))
            
            # Extract assignee and epic - handle direct string format
            assignee = raw_issue.get("assignee", "")
            epic = raw_issue.get("epic", "")
            
            # Extract all status transition dates from changelog
            target_status_transitions = self._extract_all_status_transitions(raw_issue)
            
            return JiraIssue(
                key=key,
                summary=title,
                story_points=story_points,
                created_day=created_day,
                done_day=done_day,
                due_day=due_day,
                resolution=resolution,
                labels=labels,
                components=components,
                epic=epic,
                assignee=assignee,
                status=status,
                issue_type=issue_type,
                target_status_transitions=target_status_transitions
            )
            
        except Exception as e:
            st.warning(f"Failed to normalize issue {raw_issue.get('key', 'unknown')}: {str(e)}")
            return None
    
    def _extract_story_points(self, issue_data: Dict[str, Any]) -> float:
        """Extract story points from various possible fields."""
        # Try common story points field names
        story_points_fields = [
            "story_points", "storypoints", "customfield_10016", 
            "customfield_10002", "points", "estimate"
        ]
        
        for field in story_points_fields:
            value = issue_data.get(field)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        
        return 0.0
    
    def _parse_date_field(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string to date object."""
        if not date_str:
            return None
        
        try:
            # Handle various date formats
            if isinstance(date_str, str):
                # Remove timezone info for date-only extraction
                parsed_dt = parse_date(date_str)
                return parsed_dt.date()
            return None
        except Exception:
            return None
    
    def extract_status_transition_date(self, issue_data: Dict[str, Any], target_status: str) -> Optional[date]:
        """Extract the date when issue first transitioned to target status."""
        changelog = issue_data.get("changelog", {})
        histories = changelog.get("histories", []) if changelog else []
        
        for history in histories:
            created = history.get("created")
            if not created:
                continue
                
            for item in history.get("items", []):
                if item.get("field") == "status" and item.get("toString") == target_status:
                    # Found first transition to target status
                    return self._parse_date_field(created)
        
        return None
    
    def _extract_all_status_transitions(self, issue_data: Dict[str, Any]) -> Dict[str, Optional[date]]:
        """Extract first transition date for all statuses from changelog."""
        transitions = {}
        changelog = issue_data.get("changelog", {})
        histories = changelog.get("histories", []) if changelog else []
        
        for history in histories:
            created = history.get("created")
            if not created:
                continue
                
            for item in history.get("items", []):
                if item.get("field") == "status":
                    to_status = item.get("toString")
                    if to_status and to_status not in transitions:
                        # Store first transition to this status
                        transitions[to_status] = self._parse_date_field(created)
        
        return transitions
    
    def _extract_done_day(self, issue_data: Dict[str, Any]) -> Optional[date]:
        """Extract the day when issue was first marked as done."""
        # Try to find transition to "Done" status from changelog
        done_date = self.extract_status_transition_date(issue_data, "Done")
        if done_date:
            return done_date
        
        # Fallback: if status indicates done, but no transition found
        status = issue_data.get("status", "").lower()
        done_statuses = ["done", "closed", "resolved", "complete"]
        
        if any(done_status in status for done_status in done_statuses):
            # Would need actual transition date from changelog
            return None
        
        return None
    
    def _extract_list_field(self, field_data: Any) -> List[str]:
        """Extract list of strings from various field formats."""
        if not field_data:
            return []
        
        if isinstance(field_data, str):
            return [s.strip() for s in field_data.split(",") if s.strip()]
        elif isinstance(field_data, list):
            result = []
            for item in field_data:
                if isinstance(item, str):
                    result.append(item.strip())
                elif isinstance(item, dict) and "name" in item:
                    result.append(item["name"])
            return result
        
        return []
    
    def _extract_assignee(self, assignee_data: Any) -> str:
        """Extract assignee name from various formats."""
        if not assignee_data:
            return ""
        
        if isinstance(assignee_data, str):
            return assignee_data
        elif isinstance(assignee_data, dict):
            return assignee_data.get("displayName", assignee_data.get("name", ""))
        
        return ""
    
    def build_field_catalogs(self, issues: List[JiraIssue]) -> FieldCatalogs:
        """Build catalogs of unique field values from issues."""
        catalogs = FieldCatalogs()
        
        for issue in issues:
            # Collect unique values
            if issue.status:
                catalogs.statuses.append(issue.status)
            if issue.resolution:
                catalogs.resolutions.append(issue.resolution)
            if issue.assignee:
                catalogs.assignees.append(issue.assignee)
            if issue.epic:
                catalogs.epics.append(issue.epic)
            
            catalogs.labels.extend(issue.labels)
            catalogs.components.extend(issue.components)
        
        # Remove duplicates and sort
        catalogs.statuses = sorted(list(set(catalogs.statuses)))
        catalogs.resolutions = sorted(list(set(catalogs.resolutions)))
        catalogs.assignees = sorted(list(set(catalogs.assignees)))
        catalogs.epics = sorted(list(set(catalogs.epics)))
        catalogs.labels = sorted(list(set(catalogs.labels)))
        catalogs.components = sorted(list(set(catalogs.components)))
        
        return catalogs


# Singleton instance
jira_fetcher = JiraFetcher()
