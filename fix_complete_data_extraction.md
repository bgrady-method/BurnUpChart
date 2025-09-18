# Fix Complete Jira Data Extraction

## Problem
The current data pipeline only extracts basic fields from Jira issues (key, summary, type, status, created date) but missing critical fields like **story points, assignees, epics, labels, and components**. This is because the Jira search API returns limited metadata.

## Root Cause
The MCP Atlassian server's `jira_search` endpoint returns simplified issue data:
```json
{
  "key": "PL-57198",
  "summary": "Canvas functional testing", 
  "type": "QA Task",
  "status": "To Do",
  "created": "2025-09-16",
  "priority": "None",
  "link": "https://method.atlassian.net/browse/PL-57198"
}
```

But we need complete issue data including:
- Story points (`customfield_10016` or similar)
- Assignee information
- Epic links
- Labels and components
- Due dates
- Changelog for status transitions

## Solution

### Step 1: Enable Detailed Fetching in `app.py`

Replace the current basic fetching with detailed fetching for each issue:

```python
# In fetch_jira_data() function, replace the enrichment loop:

for i, issue_data in enumerate(issues_data):
    try:
        # Get issue key for detailed fetch
        issue_key = issue_data.get("key") if isinstance(issue_data, dict) else None
        
        if issue_key:
            # Fetch detailed issue data with ALL fields
            detailed_issue = call_mcp_tool(
                "github.com/pashpashpash/mcp-atlassian",
                "jira_get_issue", 
                {
                    "issue_key": issue_key,
                    "expand": "changelog,fields"  # Ensure we get all fields
                }
            )
            
            # Add detailed metadata debug
            st.info(f"📋 Detailed issue {issue_key} fields: {list(detailed_issue.get('metadata', {}).keys()) if detailed_issue else 'None'}")
            
            # Use detailed issue data as primary source
            if detailed_issue and isinstance(detailed_issue, dict):
                enriched_issues.append(detailed_issue)
            else:
                # Fallback to search result only
                enriched_issues.append(issue_data)
        else:
            enriched_issues.append(issue_data)
            
        # Update progress
        progress_bar.progress((i + 1) / len(issues_data))
        
    except Exception as detail_error:
        st.warning(f"Failed to get details for {issue_key}: {str(detail_error)}")
        # Use original issue data as fallback
        enriched_issues.append(issue_data)
```

### Step 2: Fix Data Extraction in `fetch.py`

Update the `normalize_issue()` function to handle detailed issue data:

```python
def normalize_issue(self, raw_issue: Dict[str, Any], timezone: str = "America/Toronto") -> Optional[JiraIssue]:
    """Convert raw Jira issue data to normalized JiraIssue model."""
    try:
        # Extract basic fields
        key = raw_issue.get("key", "")
        if not key:
            return None
        
        # Get detailed fields from metadata and content
        metadata = raw_issue.get("metadata", {})
        content = raw_issue.get("content", "")
        
        # Debug: Show what fields are available
        if metadata:
            st.info(f"🔍 Available metadata fields for {key}: {list(metadata.keys())}")
        
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
        
        # Extract dates
        created_day = self._parse_date_field(
            raw_issue.get("created") or metadata.get("created")
        )
        due_day = self._parse_date_field(
            metadata.get("duedate") or metadata.get("due")
        )
        
        # Extract assignee
        assignee = self._extract_assignee_from_metadata(metadata)
        
        # Extract epic
        epic = self._extract_epic_from_metadata(metadata)
        
        # Extract labels and components
        labels = self._extract_labels_from_metadata(metadata)
        components = self._extract_components_from_metadata(metadata)
        
        # Extract resolution
        resolution = metadata.get("resolution", "")
        
        # Extract status transitions from changelog
        target_status_transitions = self._extract_all_status_transitions(raw_issue)
        
        # Extract done day from transitions
        done_day = self._extract_done_day_from_transitions(target_status_transitions)
        
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

def _extract_done_day_from_transitions(self, transitions: Dict[str, Optional[date]]) -> Optional[date]:
    """Extract done day from status transitions."""
    done_statuses = ["Done", "Closed", "Resolved", "Complete"]
    
    done_dates = []
    for status in done_statuses:
        if status in transitions and transitions[status]:
            done_dates.append(transitions[status])
    
    if done_dates:
        return min(done_dates)  # Return earliest "done" transition
    
    return None
```

### Step 3: Test and Debug

1. **Add the debug lines** to see what fields are actually available in the detailed API response
2. **Run the application** and fetch data to see the debug output
3. **Adjust field extraction** based on the actual field names returned
4. **Remove debug lines** once extraction is working correctly

### Step 4: Performance Considerations

⚠️ **Warning**: This approach will be slower because it makes individual API calls for each issue (50+ calls instead of 1), but it will provide complete data.

To optimize:
- Consider caching detailed issue data
- Implement batch processing if the MCP server supports it
- Add option to toggle between fast (basic) vs complete (detailed) data fetching

## Expected Result

After implementing this fix, the issues summary CSV should contain:
- ✅ Story points (actual values instead of 0.0)
- ✅ Created, due, and done dates
- ✅ Assignees, epics, labels, components
- ✅ Complete status transition history
- ✅ All other detailed Jira fields

## Implementation Steps

1. **Backup current code**
2. **Add debug lines to see detailed API response structure**  
3. **Update extraction functions based on actual field names**
4. **Test with a few issues first**
5. **Scale up once working correctly**
6. **Remove debug output for production**
