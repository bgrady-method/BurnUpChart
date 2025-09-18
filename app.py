import streamlit as st
import json
import pandas as pd
from datetime import date, datetime
from typing import List, Dict, Any, Optional
import plotly.graph_objects as go

# Import our modules
from models import AppConfig, JiraIssue, FieldCatalogs, ComputeResults
from fetch import jira_fetcher
from transform import data_transformer
from ui_helpers import (
    render_sidebar_controls, render_kpi_cards, create_scope_completed_chart,
    create_download_button, render_validation_report, render_empty_state,
    export_chart_png, render_help_modal
)

# Page configuration
st.set_page_config(
    page_title="Scope vs Completed (Jira)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
def initialize_session_state():
    """Initialize session state with default values."""
    if "current_config" not in st.session_state:
        st.session_state.current_config = AppConfig()
    
    if "raw_issues" not in st.session_state:
        st.session_state.raw_issues = []
    
    if "normalized_issues" not in st.session_state:
        st.session_state.normalized_issues = []
    
    if "filtered_issues" not in st.session_state:
        st.session_state.filtered_issues = []
    
    if "field_catalogs" not in st.session_state:
        st.session_state.field_catalogs = FieldCatalogs()
    
    if "compute_results" not in st.session_state:
        st.session_state.compute_results = None
    
    if "fetch_error" not in st.session_state:
        st.session_state.fetch_error = ""
    
    if "show_help" not in st.session_state:
        st.session_state.show_help = False
    
    # Set up MCP call function for fetch module
    if "mcp_call_function" not in st.session_state:
        st.session_state.mcp_call_function = call_mcp_tool

def call_mcp_tool(server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Call MCP tool using Streamlit's interface."""
    # Check if this is the first call to avoid repeated warnings
    if "mcp_connection_checked" not in st.session_state:
        st.session_state.mcp_connection_checked = False
        st.session_state.mcp_available = False
    
    # Try MCP connection methods (only show warnings on first attempt)
    try:
        # Try the Cline MCP interface first
        if hasattr(st, 'connection') and hasattr(st.connection, 'mcp'):
            result = st.connection.mcp.call_tool(server_name, tool_name, arguments)
            st.session_state.mcp_available = True
            return result
        
        # Try direct client if available
        if "mcp_client" in st.session_state:
            client = st.session_state.mcp_client
            result = client.call_tool(tool_name, arguments)
            st.session_state.mcp_available = True
            return result
            
        # Try importing MCP tools
        try:
            from st_mcp import use_mcp_tool
            result = use_mcp_tool(server_name, tool_name, arguments)
            st.session_state.mcp_available = True
            return result
        except ImportError:
            pass
        
        # If we get here, MCP is not available - show warning only once
        if not st.session_state.mcp_connection_checked:
            st.warning("⚠️ MCP connection not available - using golden dataset as fallback")
            st.session_state.mcp_connection_checked = True
            
        # Fallback to golden dataset
        if tool_name == "jira_search":
            return load_golden_dataset()
        elif tool_name == "jira_get_issue":
            golden_data = load_golden_dataset()
            issue_key = arguments.get("issue_key", "")
            for issue in golden_data:
                if issue["key"] == issue_key:
                    return {"content": f"Issue: {issue['key']}\nTitle: {issue['summary']}", "metadata": issue}
            return None
        return None
        
    except Exception as e:
        # Only show error once
        if not st.session_state.mcp_connection_checked:
            st.error(f"MCP call failed: {str(e)} - falling back to golden dataset")
            st.session_state.mcp_connection_checked = True
        
        # Fallback to golden dataset on error
        if tool_name == "jira_search":
            return load_golden_dataset()
        return None

def load_golden_dataset() -> List[Dict[str, Any]]:
    """Load the golden dataset for testing."""
    try:
        with open("golden_dataset.json", "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load golden dataset: {str(e)}")
        return []

def fetch_jira_data(config: AppConfig) -> bool:
    """Fetch data from Jira and normalize it."""
    try:
        with st.spinner("🔄 Fetching LIVE issues from Jira via MCP..."):
            start_time = datetime.now()
            
            # Fetch live data using the MCP search
            try:
                # Use MCP jira_search with the configured JQL
                raw_data = call_mcp_tool(
                    "github.com/pashpashpash/mcp-atlassian",
                    "jira_search",
                    {
                        "jql": config.jql,
                        "fields": "*all",
                        "limit": 50
                    }
                )
                
                # Check if we got valid data
                if not raw_data:
                    st.session_state.fetch_error = "No data returned from Jira search"
                    return False
                    
                # If raw_data is a list, use it directly; if wrapped in metadata, extract it
                if isinstance(raw_data, dict) and "issues" in raw_data:
                    issues_data = raw_data["issues"]
                elif isinstance(raw_data, list):
                    issues_data = raw_data
                else:
                    # Try to use the raw data as is
                    issues_data = raw_data if isinstance(raw_data, list) else [raw_data]
                
                st.info(f"📡 Successfully fetched {len(issues_data)} live issues from Jira")
                
            except Exception as mcp_error:
                st.warning(f"⚠️ MCP connection failed ({str(mcp_error)}) - using golden dataset as fallback")
                issues_data = load_golden_dataset()
            
            if not issues_data:
                st.session_state.fetch_error = "No data returned from query"
                return False
            
            # For live data, we need to fetch detailed information including changelogs
            enriched_issues = []
            progress_bar = st.progress(0)
            
            for i, issue_data in enumerate(issues_data):
                try:
                    # Get issue key for detailed fetch
                    issue_key = issue_data.get("key") if isinstance(issue_data, dict) else None
                    
                    if issue_key:
                        # Fetch detailed issue data with changelog
                        detailed_issue = call_mcp_tool(
                            "github.com/pashpashpash/mcp-atlassian",
                            "jira_get_issue", 
                            {
                                "issue_key": issue_key,
                                "expand": "changelog"
                            }
                        )
                        
                        # Merge the detailed data with search result
                        if detailed_issue and isinstance(detailed_issue, dict):
                            # Combine search result with detailed metadata
                            merged_issue = {**issue_data}
                            if "metadata" in detailed_issue:
                                merged_issue.update(detailed_issue["metadata"])
                            enriched_issues.append(merged_issue)
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
            
            progress_bar.empty()
            
            # Normalize the issues
            normalized_issues = []
            for raw_issue in enriched_issues:
                normalized = jira_fetcher.normalize_issue(raw_issue, config.timezone)
                if normalized:
                    normalized_issues.append(normalized)
            
            # Update session state
            st.session_state.raw_issues = enriched_issues
            st.session_state.normalized_issues = normalized_issues
            st.session_state.field_catalogs = jira_fetcher.build_field_catalogs(normalized_issues)
            st.session_state.fetch_error = ""
            
            # Show success toast
            duration = (datetime.now() - start_time).total_seconds()
            st.toast(f"📡 Fetched {len(normalized_issues)} LIVE issues in {duration:.1f}s", icon="✅")
            
            return True
            
    except Exception as e:
        error_msg = f"Failed to fetch data: {str(e)}"
        st.session_state.fetch_error = error_msg
        st.error(error_msg)
        return False

def compute_analysis(config: AppConfig) -> bool:
    """Compute the scope/completed analysis."""
    try:
        if not st.session_state.normalized_issues:
            st.warning("No issues to analyze. Please fetch data first.")
            return False
        
        with st.spinner("Computing analysis..."):
            start_time = datetime.now()
            
            # Compute results
            results = data_transformer.compute_results(
                st.session_state.normalized_issues, 
                config
            )
            
            st.session_state.compute_results = results
            
            # Show success toast
            duration = (datetime.now() - start_time).total_seconds()
            st.toast(f"Analysis computed in {duration:.1f}s", icon="📊")
            
            return True
            
    except Exception as e:
        st.error(f"Analysis failed: {str(e)}")
        return False

def reset_filters():
    """Reset all filters to default values."""
    default_config = AppConfig()
    default_config.jql = st.session_state.current_config.jql
    default_config.timezone = st.session_state.current_config.timezone
    default_config.cache_raw = st.session_state.current_config.cache_raw
    
    st.session_state.current_config = default_config
    st.rerun()

def main():
    """Main application function."""
    initialize_session_state()
    
    # Page header
    st.title("Scope vs Completed — Jira History")
    st.caption("X-axis is locked to max Due date; Y-axis is locked to max Scope.")
    
    # Help button
    render_help_modal()
    
    # Sidebar controls
    config, fetch_clicked, apply_clicked, reset_clicked = render_sidebar_controls(
        st.session_state.current_config,
        st.session_state.field_catalogs
    )
    
    # Update current config
    st.session_state.current_config = config
    
    # Handle button clicks
    if fetch_clicked:
        if fetch_jira_data(config):
            compute_analysis(config)
    
    if reset_clicked:
        reset_filters()
    
    if apply_clicked:
        compute_analysis(config)
    
    # Main content area
    results = st.session_state.compute_results
    
    if results is None:
        st.info("👆 Use the sidebar to fetch data and configure your analysis")
        return
    
    if results.included_issues_count == 0:
        render_empty_state()
        return
    
    # Show warnings if any
    if results.warnings:
        for warning in results.warnings:
            st.warning(warning)
    
    # KPI Cards
    render_kpi_cards(results)
    
    st.divider()
    
    # Chart Section
    st.subheader("📈 Scope vs Completed Chart")
    
    fig = create_scope_completed_chart(
        results.daily_series, 
        results.t0, 
        results.t1, 
        results.max_scope
    )
    
    st.plotly_chart(fig, use_container_width=True, key="fig_scope_completed")
    
    # Chart export
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        export_chart_png(fig)
    
    st.divider()
    
    # Weekly Status Breakdown Table
    st.subheader("📊 Weekly Status Breakdown")
    
    if st.session_state.normalized_issues:
        # Get filtered issues for weekly analysis
        filtered_issues, _ = data_transformer.apply_filters(
            st.session_state.normalized_issues, 
            config
        )
        
        if filtered_issues:
            weekly_df = data_transformer.generate_weekly_status_table(
                filtered_issues, results.t0, results.t1, config
            )
            
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col2:
                create_download_button(
                    weekly_df, "weekly_status.csv", "📥 CSV", "download_weekly_csv"
                )
            with col3:
                create_download_button(
                    weekly_df, "weekly_status.json", "📥 JSON", "download_weekly_json"
                )
            
            st.dataframe(
                weekly_df,
                use_container_width=True,
                key="grid_weekly",
                hide_index=True
            )
            
            # Add explanation
            with st.expander("📋 Status Categories & Calculations"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Done**: Done, Closed, Resolved")
                    st.write("**Target by Due Date**: Story points that should be completed by week end based on issue due dates")
                    st.write("**In Flight**: In Analysis, Done Analysis, Done Dev, In Test, Done Test, Ready to Deploy, In Dev, To Review")
                with col2:
                    st.write("**Not Started**: To Do, Ready For Development, Ready for Grooming")
                    st.write("**Blocked**: Blocked, On Hold")
                    st.write("**% Done**: (Done ÷ Total SP) × 100")
        else:
            st.info("No issues available for weekly breakdown")
    
    st.divider()
    
    # Issues Summary Table
    st.subheader("📋 Issues Summary")
    
    if st.session_state.normalized_issues:
        # Get filtered issues for display
        filtered_issues, _ = data_transformer.apply_filters(
            st.session_state.normalized_issues, 
            config
        )
        
        if filtered_issues:
            issues_df = data_transformer.issues_to_dataframe(filtered_issues)
            
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col2:
                create_download_button(
                    issues_df, "issues_summary.csv", "📥 CSV", "download_issues_csv"
                )
            with col3:
                create_download_button(
                    issues_df, "issues_summary.json", "📥 JSON", "download_issues_json"
                )
            
            st.dataframe(
                issues_df,
                use_container_width=True,
                key="grid_issues"
            )
        else:
            st.info("No issues match the current filters")
    
    st.divider()
    
    # Daily Series Table (moved to bottom)
    st.subheader("📅 Daily Series")
    
    if results.daily_series:
        daily_df = data_transformer.daily_series_to_dataframe(results.daily_series)
        
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        with col2:
            create_download_button(
                daily_df, "daily_series.csv", "📥 CSV", "download_daily_csv"
            )
        with col3:
            create_download_button(
                daily_df, "daily_series.json", "📥 JSON", "download_daily_json"
            )
        
        st.dataframe(
            daily_df,
            use_container_width=True,
            key="grid_daily"
        )
    
    # Optional sections
    if config.show_validation:
        st.divider()
        render_validation_report(results)
    
    if config.show_intermediate:
        st.divider()
        st.subheader("🔍 Intermediate Data")
        st.write("**Raw Issues Count:**", len(st.session_state.raw_issues))
        st.write("**Normalized Issues Count:**", len(st.session_state.normalized_issues))
        st.write("**Filtered Issues Count:**", results.included_issues_count)
        st.write("**Excluded Issues Count:**", results.excluded_issues_count)

if __name__ == "__main__":
    main()
