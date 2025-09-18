import logging
import os
from datetime import datetime
from typing import List, Optional

from atlassian import Jira
from dotenv import load_dotenv

from .config import JiraConfig
from .document_types import Document
from .preprocessing import TextPreprocessor

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger("mcp-jira")


class JiraFetcher:
    """Handles fetching and parsing content from Jira."""

    def __init__(self, require_credentials: bool = False):
        self.config = None
        self.jira = None
        self.preprocessor = None
        
        # Try to initialize with environment variables
        url = os.getenv("JIRA_URL")
        username = os.getenv("JIRA_USERNAME")
        token = os.getenv("JIRA_API_TOKEN")

        if all([url, username, token]):
            try:
                self.config = JiraConfig(url=url, username=username, api_token=token)
                self.jira = Jira(
                    url=self.config.url,
                    username=self.config.username,
                    password=self.config.api_token,  # API token is used as password
                    cloud=True,
                )
                self.preprocessor = TextPreprocessor(self.config.url)
            except Exception as e:
                if require_credentials:
                    raise ValueError(f"Failed to initialize Jira client: {str(e)}")
                # Allow graceful degradation for fallback system
                pass
        elif require_credentials:
            raise ValueError("Missing required Jira environment variables")
    
    def _ensure_initialized(self):
        """Ensure Jira client is initialized before use."""
        if not self.jira or not self.config:
            raise ValueError("Jira client not initialized - missing environment variables (JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)")

    def _clean_text(self, text: str) -> str:
        """
        Clean text content by:
        1. Processing user mentions and links
        2. Converting HTML/wiki markup to markdown
        """
        if not text:
            return ""

        return self.preprocessor.clean_jira_text(text)

    def _parse_date(self, date_str: str) -> str:
        """Parse date string to handle various ISO formats."""
        if not date_str:
            return ""

        # Handle various timezone formats
        if "+0000" in date_str:
            date_str = date_str.replace("+0000", "+00:00")
        elif "-0000" in date_str:
            date_str = date_str.replace("-0000", "+00:00")
        # Handle other timezone formats like +0900, -0500, etc.
        elif len(date_str) >= 5 and date_str[-5] in "+-" and date_str[-4:].isdigit():
            # Insert colon between hours and minutes of timezone
            date_str = date_str[:-2] + ":" + date_str[-2:]

        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Error parsing date {date_str}: {e}")
            return date_str

    def _extract_story_points(self, fields: dict) -> float:
        """Extract story points from various possible custom fields."""        
        # Story points field IDs for this Jira instance
        story_point_fields = [
            "customfield_10506",  # Your Jira instance story points field
            "customfield_10016",  # Most common fallback
            "customfield_10002", 
            "customfield_10004",
            "customfield_10020",
            "customfield_10021",
            "customfield_10028",
            "customfield_10037",
            "customfield_10106",
            "customfield_10024"
        ]
        
        for field_id in story_point_fields:
            value = fields.get(field_id)
            if value is not None:
                try:
                    story_points = float(value)
                    if story_points > 0:  # Found non-zero story points
                        print(f"  ✅ Story Points found in {field_id}: {story_points}")
                    return story_points
                except (ValueError, TypeError):
                    continue
        
        return 0.0

    def _extract_assignee(self, assignee_data) -> str:
        """Extract assignee display name from Jira assignee object."""
        if not assignee_data:
            return ""
        
        if isinstance(assignee_data, dict):
            return assignee_data.get("displayName", assignee_data.get("name", ""))
        elif isinstance(assignee_data, str):
            return assignee_data
        
        return ""

    def _extract_epic_link(self, fields: dict) -> str:
        """Extract epic link from various possible fields."""
        # Common epic link field IDs
        epic_fields = [
            "customfield_10014",  # Most common Epic Link field
            "customfield_10008",
            "customfield_10009",
            "parent"  # For sub-tasks
        ]
        
        for field_id in epic_fields:
            epic_data = fields.get(field_id)
            if epic_data:
                if isinstance(epic_data, str):
                    return epic_data
                elif isinstance(epic_data, dict):
                    return epic_data.get("key", epic_data.get("name", ""))
        
        return ""

    def _extract_labels(self, labels_data) -> List[str]:
        """Extract labels from Jira labels field."""
        if not labels_data:
            return []
        
        if isinstance(labels_data, list):
            return [str(label) for label in labels_data]
        elif isinstance(labels_data, str):
            return [label.strip() for label in labels_data.split(",") if label.strip()]
        
        return []

    def _extract_components(self, components_data) -> List[str]:
        """Extract component names from Jira components field."""
        if not components_data:
            return []
        
        if isinstance(components_data, list):
            result = []
            for comp in components_data:
                if isinstance(comp, dict):
                    result.append(comp.get("name", ""))
                elif isinstance(comp, str):
                    result.append(comp)
            return result
        elif isinstance(components_data, str):
            return [comp.strip() for comp in components_data.split(",") if comp.strip()]
        
        return []

    def get_issue(self, issue_key: str, expand: Optional[str] = None) -> Document:
        """
        Get a single issue with all its details.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            expand: Optional fields to expand

        Returns:
            Document containing issue content and metadata
        """
        self._ensure_initialized()
        try:
            issue = self.jira.issue(issue_key, expand=expand)

            # Process description and comments
            description = self._clean_text(issue["fields"].get("description", ""))

            # Get comments
            comments = []
            if "comment" in issue["fields"]:
                for comment in issue["fields"]["comment"]["comments"]:
                    processed_comment = self._clean_text(comment["body"])
                    created = self._parse_date(comment["created"])
                    author = comment["author"].get("displayName", "Unknown")
                    comments.append({"body": processed_comment, "created": created, "author": author})

            # Format created date using new parser
            created_date = self._parse_date(issue["fields"]["created"])

            # Combine content in a more structured way
            content = f"""Issue: {issue_key}
Title: {issue['fields'].get('summary', '')}
Type: {issue['fields']['issuetype']['name']}
Status: {issue['fields']['status']['name']}
Created: {created_date}

Description:
{description}

Comments:
""" + "\n".join(
                [f"{c['created']} - {c['author']}: {c['body']}" for c in comments]
            )

            # Extract enhanced fields with debugging
            story_points = self._extract_story_points(issue["fields"])
            assignee = self._extract_assignee(issue["fields"].get("assignee"))
            epic_link = self._extract_epic_link(issue["fields"])
            labels = self._extract_labels(issue["fields"].get("labels", []))
            components = self._extract_components(issue["fields"].get("components", []))
            
            # Debug: Show successful extraction summary
            print(f"✅ EXTRACTION - {issue_key}: SP={story_points}, assignee='{assignee}', epic='{epic_link}', labels={len(labels)}, components={len(components)}")
            
            # Comprehensive metadata with all needed fields
            metadata = {
                "key": issue_key,
                "title": issue["fields"].get("summary", ""),
                "summary": issue["fields"].get("summary", ""),  # Add summary alias
                "type": issue["fields"]["issuetype"]["name"],
                "issuetype": issue["fields"]["issuetype"]["name"],  # Add issuetype alias
                "status": issue["fields"]["status"]["name"],
                "created": issue["fields"]["created"],  # Keep original format for created
                "created_date": created_date,
                "priority": issue["fields"].get("priority", {}).get("name", "None") if issue["fields"].get("priority") else "None",
                "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
                
                # Extract story points from multiple possible fields
                "story_points": story_points,
                "storypoints": story_points,  # Alias
                
                # Extract assignee
                "assignee": assignee,
                
                # Extract epic link
                "epic": epic_link,
                "epic_link": epic_link,  # Alias
                
                # Extract labels
                "labels": labels,
                
                # Extract components
                "components": components,
                
                # Extract dates
                "duedate": self._parse_date(issue["fields"].get("duedate")) if issue["fields"].get("duedate") else None,
                "due": self._parse_date(issue["fields"].get("duedate")) if issue["fields"].get("duedate") else None,  # Alias
                
                # Extract resolution
                "resolution": issue["fields"].get("resolution", {}).get("name", "") if issue["fields"].get("resolution") else "",
            }
            
            # Add changelog if expand was requested
            if expand and "changelog" in expand and "changelog" in issue:
                metadata["changelog"] = issue["changelog"]
                print(f"  📜 Changelog entries: {len(issue['changelog'].get('histories', []))}")

            return Document(page_content=content, metadata=metadata)

        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            raise

    def search_issues(
        self, jql: str, fields: str = "*all", start: int = 0, limit: int = 50, expand: Optional[str] = None
    ) -> List[Document]:
        """
        Search for issues using JQL.

        Args:
            jql: JQL query string
            fields: Comma-separated string of fields to return
            start: Starting index
            limit: Maximum results to return
            expand: Fields to expand

        Returns:
            List of Documents containing matching issues
        """
        self._ensure_initialized()
        try:
            results = self.jira.jql(jql, fields=fields, start=start, limit=limit, expand=expand)

            documents = []
            for issue in results["issues"]:
                # Get full issue details
                doc = self.get_issue(issue["key"], expand=expand)
                documents.append(doc)

            return documents

        except Exception as e:
            logger.error(f"Error searching issues with JQL {jql}: {str(e)}")
            raise

    def get_project_issues(self, project_key: str, start: int = 0, limit: int = 50) -> List[Document]:
        """
        Get all issues for a project.

        Args:
            project_key: The project key
            start: Starting index
            limit: Maximum results to return

        Returns:
            List of Documents containing project issues
        """
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)

    def get_issue_metadata(self, issue_key: str, include_transitions: bool = True, 
                          include_edit_meta: bool = True, include_field_schema: bool = True) -> dict:
        """
        Get comprehensive issue metadata including transitions and field requirements.
        
        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            include_transitions: Include available transitions
            include_edit_meta: Include editable field metadata
            include_field_schema: Include field schema information
            
        Returns:
            Dictionary containing comprehensive issue metadata
        """
        try:
            # Get basic issue info
            issue = self.jira.issue(issue_key)
            
            result = {
                "issue": {
                    "key": issue_key,
                    "status": issue["fields"]["status"]["name"],
                    "type": issue["fields"]["issuetype"]["name"]
                }
            }
            
            # Get available transitions
            if include_transitions:
                transitions_response = self.jira.get_issue_transitions(issue_key)
                transitions = []
                
                # Handle both dict and list responses
                transitions_list = transitions_response
                if isinstance(transitions_response, dict):
                    transitions_list = transitions_response.get("transitions", [])
                
                for transition in transitions_list:
                    transition_data = {
                        "id": transition["id"],
                        "name": transition["name"],
                        "required_fields": [],
                        "optional_fields": [],
                        "validation_rules": []
                    }
                    
                    # Extract field requirements from transition
                    if "fields" in transition:
                        for field_id, field_info in transition["fields"].items():
                            if field_info.get("required", False):
                                transition_data["required_fields"].append(field_id)
                            else:
                                transition_data["optional_fields"].append(field_id)
                    
                    transitions.append(transition_data)
                
                result["available_transitions"] = transitions
            
            # Get editable fields metadata
            if include_edit_meta:
                edit_meta = self.jira.issue_editmeta(issue_key)
                editable_fields = {}
                
                # Handle both dict and list responses
                if isinstance(edit_meta, dict) and "fields" in edit_meta:
                    for field_id, field_info in edit_meta["fields"].items():
                        field_data = {
                            "name": field_info.get("name", field_id),
                            "type": field_info.get("schema", {}).get("type", "unknown"),
                            "required": field_info.get("required", False),
                            "schema": field_info.get("schema", {})
                        }
                        
                        # Add allowed values if available
                        if "allowedValues" in field_info:
                            field_data["allowed_values"] = [
                                val.get("value", val.get("name", str(val))) 
                                for val in field_info["allowedValues"]
                            ]
                        
                        editable_fields[field_id] = field_data
                
                result["editable_fields"] = editable_fields
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting issue metadata for {issue_key}: {str(e)}")
            raise

    def discover_custom_fields(self, project_key: str, issue_type: Optional[str] = None) -> dict:
        """
        Discover and map custom field IDs to their names and purposes.
        
        Args:
            project_key: Project key to discover fields for
            issue_type: Optional issue type to filter fields
            
        Returns:
            Dictionary mapping custom field IDs to their metadata
        """
        try:
            # Get all fields
            all_fields = self.jira.get_all_fields()
            
            custom_fields = {}
            
            try:
                # Try the new API first (Jira 9+)
                if issue_type:
                    create_meta = self.jira.issue_createmeta_issuetypes(project=project_key, issuetype=issue_type)
                else:
                    create_meta = self.jira.issue_createmeta_issuetypes(project=project_key)
                
                # Process new API response format
                if isinstance(create_meta, dict) and "issueTypes" in create_meta:
                    issue_types = create_meta["issueTypes"]
                    for issue_type_data in issue_types:
                        fields = issue_type_data.get("fields", {}) if isinstance(issue_type_data, dict) else {}
                        for field_id, field_data in fields.items():
                            if field_id.startswith("customfield_"):
                                # Find additional info from all_fields
                                field_info = next((f for f in all_fields if f.get("id") == field_id), {})
                                
                                custom_fields[field_id] = {
                                    "id": field_id,
                                    "name": field_data.get("name", field_id) if isinstance(field_data, dict) else field_id,
                                    "description": field_info.get("description", "") if isinstance(field_info, dict) else "",
                                    "type": field_data.get("schema", {}).get("type", "unknown") if isinstance(field_data, dict) else "unknown",
                                    "context": [issue_type_data.get("name", "unknown")] if isinstance(issue_type_data, dict) else ["unknown"]
                                }
                else:
                    raise Exception("Unexpected response format from new API")
                    
            except (AttributeError, Exception) as new_api_error:
                # Fallback to deprecated API for older Jira versions
                try:
                    expand = "projects.issuetypes.fields"
                    if issue_type:
                        expand += f",projects.issuetypes.{issue_type}.fields"
                    create_meta = self.jira.issue_createmeta(project=project_key, expand=expand)
                    
                    # Process deprecated API response format
                    projects = create_meta.get("projects", []) if isinstance(create_meta, dict) else []
                    for project in projects:
                        issue_types = project.get("issuetypes", []) if isinstance(project, dict) else []
                        for issue_type_data in issue_types:
                            fields = issue_type_data.get("fields", {}) if isinstance(issue_type_data, dict) else {}
                            for field_id, field_data in fields.items():
                                if field_id.startswith("customfield_"):
                                    # Find additional info from all_fields
                                    field_info = next((f for f in all_fields if f.get("id") == field_id), {})
                                    
                                    custom_fields[field_id] = {
                                        "id": field_id,
                                        "name": field_data.get("name", field_id) if isinstance(field_data, dict) else field_id,
                                        "description": field_info.get("description", "") if isinstance(field_info, dict) else "",
                                        "type": field_data.get("schema", {}).get("type", "unknown") if isinstance(field_data, dict) else "unknown",
                                        "context": [issue_type_data.get("name", "unknown")] if isinstance(issue_type_data, dict) else ["unknown"]
                                    }
                                    
                except Exception as fallback_error:
                    logger.warning(f"Both new and deprecated APIs failed, using field list only. New API error: {new_api_error}, Deprecated API error: {fallback_error}")
                    # If both APIs fail, just return custom fields from all_fields
                    for field in all_fields:
                        if isinstance(field, dict) and field.get("id", "").startswith("customfield_"):
                            field_id = field["id"]
                            custom_fields[field_id] = {
                                "id": field_id,
                                "name": field.get("name", field_id),
                                "description": field.get("description", ""),
                                "type": field.get("schema", {}).get("type", "unknown") if isinstance(field.get("schema"), dict) else "unknown",
                                "context": ["unknown"]
                            }
                    return {"custom_fields": custom_fields}
            
            return {"custom_fields": custom_fields}
            
        except Exception as e:
            logger.error(f"Error discovering custom fields for project {project_key}: {str(e)}")
            raise

    def get_transitions(self, issue_key: str) -> list:
        """
        Get available transitions for an issue.
        
        Args:
            issue_key: The issue key
            
        Returns:
            List of available transitions
        """
        try:
            response = self.jira.get_issue_transitions(issue_key)
            # Handle both dict and list responses
            if isinstance(response, dict):
                return response.get("transitions", [])
            elif isinstance(response, list):
                return response
            else:
                return []
        except Exception as e:
            logger.error(f"Error getting transitions for {issue_key}: {str(e)}")
            raise

    def transition_issue(self, issue_key: str, transition_id: str, fields: Optional[dict] = None) -> dict:
        """
        Transition an issue to a new status.
        
        Args:
            issue_key: The issue key
            transition_id: ID of the transition to perform
            fields: Optional fields to update during transition
            
        Returns:
            Result of the transition operation
        """
        try:
            import requests
            
            # Use direct API call to avoid atlassian library bug
            auth = (self.config.username, self.config.api_token)
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            
            transition_url = f"{self.config.url.rstrip('/')}/rest/api/3/issue/{issue_key}/transitions"
            transition_data = {"transition": {"id": transition_id}}
            
            if fields:
                transition_data["fields"] = fields
                
            response = requests.post(transition_url, json=transition_data, auth=auth, headers=headers)
            
            if response.status_code == 204:
                return {"success": True, "message": f"Issue {issue_key} transitioned successfully"}
            else:
                error_msg = f"Transition failed: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
        except Exception as e:
            logger.error(f"Error transitioning issue {issue_key}: {str(e)}")
            raise

    def transition_with_validation(self, issue_key: str, transition_id: str, 
                                 fields: Optional[dict] = None, validate_only: bool = False) -> dict:
        """
        Transition an issue with pre-validation and better error handling.
        
        Args:
            issue_key: The issue key
            transition_id: ID of the transition to perform
            fields: Optional fields to update during transition
            validate_only: Only validate, do not execute transition
            
        Returns:
            Result of validation or transition
        """
        try:
            # Get available transitions
            transitions = self.get_transitions(issue_key)
            transition = next((t for t in transitions if str(t.get("id")) == str(transition_id)), None)
            
            if not transition:
                raise ValueError(f"Transition {transition_id} not available for issue {issue_key}")
            
            # Validate required fields
            required_fields = []
            if isinstance(transition, dict) and "fields" in transition:
                required_fields = [
                    field_id for field_id, field_info in transition["fields"].items()
                    if isinstance(field_info, dict) and field_info.get("required", False)
                ]
            
            missing_fields = [field for field in required_fields if not fields or field not in fields]
            
            if missing_fields:
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
            
            if validate_only:
                return {
                    "valid": True,
                    "transition": transition,
                    "required_fields": required_fields
                }
            
            # Perform the transition
            return self.transition_issue(issue_key, transition_id, fields)
            
        except Exception as e:
            logger.error(f"Error in transition validation for {issue_key}: {str(e)}")
            raise

    def update_issue(self, issue_key: str, fields: dict) -> dict:
        """
        Update an issue with new field values.
        
        Args:
            issue_key: The issue key
            fields: Dictionary of fields to update
            
        Returns:
            Result of the update operation
        """
        try:
            self.jira.update_issue_field(issue_key, fields)
            return {"success": True, "message": f"Issue {issue_key} updated successfully"}
            
        except Exception as e:
            logger.error(f"Error updating issue {issue_key}: {str(e)}")
            raise

    def assign_issue(self, issue_key: str, assignee: str) -> dict:
        """
        Assign an issue to a user.
        
        Args:
            issue_key: The issue key
            assignee: Username or account ID of the assignee
            
        Returns:
            Result of the assignment operation
        """
        try:
            self.jira.assign_issue(issue_key, assignee)
            return {"success": True, "message": f"Issue {issue_key} assigned to {assignee}"}
            
        except Exception as e:
            logger.error(f"Error assigning issue {issue_key}: {str(e)}")
            raise

    def add_comment(self, issue_key: str, comment: str) -> dict:
        """
        Add a comment to an issue.
        
        Args:
            issue_key: The issue key
            comment: Comment text to add
            
        Returns:
            Result of the comment operation
        """
        try:
            self.jira.issue_add_comment(issue_key, comment)
            return {"success": True, "message": f"Comment added to issue {issue_key}"}
            
        except Exception as e:
            logger.error(f"Error adding comment to issue {issue_key}: {str(e)}")
            raise

    def bulk_update_and_transition(self, issue_keys: List[str], field_updates: dict, 
                                 transition_path: Optional[List[str]] = None, 
                                 stop_on_error: bool = True) -> dict:
        """
        Update multiple issues with the same field values and transition them.
        
        Args:
            issue_keys: List of issue keys to update
            field_updates: Fields to update on all issues
            transition_path: Optional list of transition IDs to execute in sequence
            stop_on_error: Stop processing if an error occurs
            
        Returns:
            Results of bulk operations
        """
        results = []
        
        for issue_key in issue_keys:
            try:
                # Update fields if provided
                if field_updates:
                    self.update_issue(issue_key, field_updates)
                
                # Execute transition path if provided
                if transition_path:
                    for transition_id in transition_path:
                        self.transition_issue(issue_key, transition_id)
                
                results.append({"issue_key": issue_key, "status": "success"})
                
            except Exception as e:
                error_msg = str(e)
                results.append({"issue_key": issue_key, "status": "error", "error": error_msg})
                logger.error(f"Error processing issue {issue_key}: {error_msg}")
                
                if stop_on_error:
                    break
        
        return {"results": results}
