import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import streamlit as st
from dateutil.parser import parse as parse_date
from models import JiraIssue, FieldCatalogs

# Import local MCP components as fallback
try:
    from mcp_atlassian.jira import JiraFetcher as LocalJiraFetcher
    LOCAL_JIRA_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Local Jira components not available: {e}")
    LOCAL_JIRA_AVAILABLE = False


class JiraFetcher:
    """Fetches and processes Jira data via MCP server or local fallback."""
    
    def __init__(self):
        self.mcp_server_name = "github.com/pashpashpash/mcp-atlassian"
        self.local_jira = None
        
        # Initialize local Jira fallback if available
        if LOCAL_JIRA_AVAILABLE:
            try:
                self.local_jira = LocalJiraFetcher()
                print("Local Jira fallback initialized successfully")
            except Exception as e:
                print(f"Failed to initialize local Jira fallback: {e}")
                self.local_jira = None
    
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
            # Extract key from multiple possible locations
            key = (raw_issue.get("key", "") or 
                   raw_issue.get("metadata", {}).get("key", ""))
            
            if not key:
                print(f"❌ NO KEY FOUND in raw_issue structure:")
                print(f"   Top-level keys: {list(raw_issue.keys())}")
                if 'metadata' in raw_issue:
                    print(f"   Metadata keys: {list(raw_issue['metadata'].keys())}")
                print(f"   First 200 chars of raw_issue: {str(raw_issue)[:200]}...")
                return None
            
            # Get detailed fields from metadata and content
            metadata = raw_issue.get("metadata", {})
            content = raw_issue.get("content", "")
            
            # Debug: Print available metadata fields
            print(f"🔍 DEBUG - Issue {key} metadata fields: {list(metadata.keys())}")
            print(f"🔍 DEBUG - Issue {key} top-level fields: {list(raw_issue.keys())}")
            
            # Extract basic fields with fallbacks
            title = (raw_issue.get("summary", "") or 
                    metadata.get("summary", "") or
                    metadata.get("title", ""))
            
            status = (raw_issue.get("status", "") or
                     metadata.get("status", ""))
            
            issue_type = (raw_issue.get("type", "") or
                         metadata.get("type", "") or
                         metadata.get("issuetype", ""))
            
            # Extract story points from multiple possible fields
            story_points = self._extract_story_points_from_metadata(metadata)
            print(f"📊 DEBUG - Issue {key} story points: {story_points}")
            
            # Extract dates
            created_day = self._parse_date_field(
                raw_issue.get("created") or metadata.get("created") or metadata.get("created_date")
            )
            due_day = self._parse_date_field(
                metadata.get("duedate") or metadata.get("due")
            )
            
            # Debug due date extraction
            if metadata.get("duedate") or metadata.get("due"):
                print(f"📅 DEBUG - Issue {key} due date found: duedate={metadata.get('duedate')}, due={metadata.get('due')}")
            else:
                print(f"📅 DEBUG - Issue {key} no due date found")
            
            # Extract assignee
            assignee = self._extract_assignee_from_metadata(metadata)
            print(f"👤 DEBUG - Issue {key} assignee: '{assignee}'")
            
            # Extract epic
            epic = self._extract_epic_from_metadata(metadata)
            print(f"📋 DEBUG - Issue {key} epic: '{epic}'")
            
            # Extract labels and components
            labels = self._extract_labels_from_metadata(metadata)
            components = self._extract_components_from_metadata(metadata)
            print(f"🏷️ DEBUG - Issue {key} labels: {labels}")
            print(f"🔧 DEBUG - Issue {key} components: {components}")
            
            # Extract resolution
            resolution = metadata.get("resolution", "")
            
            # Extract status transitions from changelog
            target_status_transitions = self._extract_all_status_transitions(raw_issue)
            print(f"🔄 DEBUG - Issue {key} transitions: {list(target_status_transitions.keys())}")
            
            # Extract done day from transitions using configured target status
            done_day = self._extract_done_day_from_transitions(target_status_transitions, 
                                                             getattr(st.session_state.get('current_config'), 'target_status', ''))
            
            # Create normalized JiraIssue with extracted data
            normalized_issue = JiraIssue(
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
            
            print(f"✅ NORMALIZED - {key}: SP={normalized_issue.story_points}, assignee='{normalized_issue.assignee}', epic='{normalized_issue.epic}', status='{normalized_issue.status}'")
            
            return normalized_issue
            
        except Exception as e:
            print(f"❌ ERROR - Failed to normalize issue {raw_issue.get('key', 'unknown')}: {str(e)}")
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
        
        # Look for changelog in multiple locations
        changelog = (issue_data.get("changelog") or 
                    issue_data.get("metadata", {}).get("changelog"))
        
        if not changelog:
            print(f"   🚫 No changelog found in issue_data")
            return transitions
        
        histories = changelog.get("histories", []) if isinstance(changelog, dict) else []
        print(f"   📜 Found {len(histories)} changelog histories")
        
        for history in histories:
            created = history.get("created")
            if not created:
                continue
                
            for item in history.get("items", []):
                if item.get("field") == "status":
                    to_status = item.get("toString")
                    if to_status and to_status not in transitions:
                        # Store first transition to this status
                        transition_date = self._parse_date_field(created)
                        transitions[to_status] = transition_date
                        print(f"   ➡️ Found transition to '{to_status}' on {transition_date}")
        
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
    
    def _extract_story_points_comprehensive(self, issue_data: Dict[str, Any]) -> float:
        """Extract story points from comprehensive field checking."""
        fields = issue_data.get("fields", {})
        metadata = issue_data.get("metadata", {})
        
        # Try common story points field names in multiple locations
        story_points_fields = [
            "story_points", "storypoints", "customfield_10016", 
            "customfield_10002", "customfield_10004", "points", "estimate"
        ]
        
        # Check direct issue data
        for field in story_points_fields:
            value = issue_data.get(field)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        
        # Check fields object
        for field in story_points_fields:
            value = fields.get(field)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        
        # Check metadata
        for field in story_points_fields:
            value = metadata.get(field)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        
        return 0.0
    
    def _parse_date_comprehensive(self, issue_data: Dict[str, Any], field_names: List[str]) -> Optional[date]:
        """Parse date from multiple field locations."""
        fields = issue_data.get("fields", {})
        metadata = issue_data.get("metadata", {})
        
        for field_name in field_names:
            # Check direct issue data
            date_str = issue_data.get(field_name)
            if date_str:
                parsed = self._parse_date_field(date_str)
                if parsed:
                    return parsed
            
            # Check fields object
            date_str = fields.get(field_name)
            if date_str:
                parsed = self._parse_date_field(date_str)
                if parsed:
                    return parsed
                    
            # Check metadata
            date_str = metadata.get(field_name)
            if date_str:
                parsed = self._parse_date_field(date_str)
                if parsed:
                    return parsed
        
        return None
    
    def _extract_list_field_comprehensive(self, issue_data: Dict[str, Any], field_names: List[str]) -> List[str]:
        """Extract list fields from multiple locations."""
        fields = issue_data.get("fields", {})
        metadata = issue_data.get("metadata", {})
        
        for field_name in field_names:
            # Check direct issue data
            field_data = issue_data.get(field_name)
            if field_data:
                result = self._extract_list_field(field_data)
                if result:
                    return result
            
            # Check fields object
            field_data = fields.get(field_name)
            if field_data:
                result = self._extract_list_field(field_data)
                if result:
                    return result
                    
            # Check metadata
            field_data = metadata.get(field_name)
            if field_data:
                result = self._extract_list_field(field_data)
                if result:
                    return result
        
        return []
    
    def _extract_assignee_comprehensive(self, issue_data: Dict[str, Any]) -> str:
        """Extract assignee from multiple locations and formats."""
        fields = issue_data.get("fields", {})
        metadata = issue_data.get("metadata", {})
        
        assignee_fields = ["assignee", "assigned_to"]
        
        for field_name in assignee_fields:
            # Check direct issue data
            assignee_data = issue_data.get(field_name)
            if assignee_data:
                result = self._extract_assignee(assignee_data)
                if result:
                    return result
            
            # Check fields object
            assignee_data = fields.get(field_name)
            if assignee_data:
                result = self._extract_assignee(assignee_data)
                if result:
                    return result
                    
            # Check metadata
            assignee_data = metadata.get(field_name)
            if assignee_data:
                result = self._extract_assignee(assignee_data)
                if result:
                    return result
        
        return ""
    
    def _extract_epic_comprehensive(self, issue_data: Dict[str, Any]) -> str:
        """Extract epic from multiple locations and formats."""
        fields = issue_data.get("fields", {})
        metadata = issue_data.get("metadata", {})
        
        epic_fields = ["epic", "epic_link", "customfield_10014", "parent"]
        
        for field_name in epic_fields:
            # Check direct issue data
            epic_data = issue_data.get(field_name)
            if epic_data:
                if isinstance(epic_data, str):
                    return epic_data
                elif isinstance(epic_data, dict):
                    return epic_data.get("key", epic_data.get("name", ""))
            
            # Check fields object
            epic_data = fields.get(field_name)
            if epic_data:
                if isinstance(epic_data, str):
                    return epic_data
                elif isinstance(epic_data, dict):
                    return epic_data.get("key", epic_data.get("name", ""))
                    
            # Check metadata
            epic_data = metadata.get(field_name)
            if epic_data:
                if isinstance(epic_data, str):
                    return epic_data
                elif isinstance(epic_data, dict):
                    return epic_data.get("key", epic_data.get("name", ""))
        
        return ""
    
    def _extract_story_points_from_metadata(self, metadata: Dict[str, Any]) -> float:
        """Extract story points from metadata."""
        story_point_fields = [
            "story_points", "storypoints", "customfield_10016", 
            "customfield_10002", "customfield_10004", "points", "estimate"
        ]
        
        for field in story_point_fields:
            value = metadata.get(field)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        
        # Try parsing from content if not in metadata
        content = metadata.get("content", "")
        if "Story Points:" in content:
            # Parse from content using regex
            import re
            match = re.search(r"Story Points:\s*(\d+\.?\d*)", content)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, TypeError):
                    pass
        
        return 0.0

    def _extract_assignee_from_metadata(self, metadata: Dict[str, Any]) -> str:
        """Extract assignee from metadata."""
        assignee = metadata.get("assignee")
        if assignee:
            if isinstance(assignee, str):
                return assignee
            elif isinstance(assignee, dict):
                return assignee.get("displayName", assignee.get("name", ""))
        return ""

    def _extract_epic_from_metadata(self, metadata: Dict[str, Any]) -> str:
        """Extract epic from metadata."""
        epic_fields = ["epic", "epic_link", "customfield_10014", "parent"]
        
        for field in epic_fields:
            epic = metadata.get(field)
            if epic:
                if isinstance(epic, str):
                    return epic
                elif isinstance(epic, dict):
                    return epic.get("key", epic.get("name", ""))
        return ""

    def _extract_labels_from_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        """Extract labels from metadata."""
        labels = metadata.get("labels", [])
        if isinstance(labels, list):
            return [str(label) for label in labels]
        elif isinstance(labels, str):
            return [label.strip() for label in labels.split(",") if label.strip()]
        return []

    def _extract_components_from_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        """Extract components from metadata."""
        components = metadata.get("components", [])
        if isinstance(components, list):
            result = []
            for comp in components:
                if isinstance(comp, str):
                    result.append(comp)
                elif isinstance(comp, dict):
                    result.append(comp.get("name", ""))
            return result
        elif isinstance(components, str):
            return [comp.strip() for comp in components.split(",") if comp.strip()]
        return []

    def _extract_done_day_from_transitions(self, transitions: Dict[str, Optional[date]], target_status: str = "") -> Optional[date]:
        """Extract done day from status transitions using configured target status."""
        
        # If target status is configured and available, use it
        if target_status and target_status in transitions:
            done_date = transitions[target_status]
            print(f"   🎯 Using configured target status '{target_status}': {done_date}")
            return done_date
        
        # Fallback to default done statuses
        done_statuses = ["Done", "Closed", "Resolved", "Complete"]
        done_dates = []
        for status in done_statuses:
            if status in transitions and transitions[status]:
                done_dates.append(transitions[status])
        
        if done_dates:
            earliest_done = min(done_dates)
            print(f"   📅 Using fallback done statuses: {earliest_done}")
            return earliest_done
        
        print(f"   ❌ No done date found (target: '{target_status}', available: {list(transitions.keys())})")
        return None

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
