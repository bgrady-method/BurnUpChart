import json
from datetime import date
from typing import List, Dict, Any, Optional
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import streamlit as st
from models import DailyPoint, ComputeResults, AppConfig, FieldCatalogs


def create_scope_completed_chart(daily_series: List[DailyPoint], t0: date, t1: date, max_scope: float) -> go.Figure:
    """Create the main scope vs completed chart with strict axis locks."""
    if not daily_series:
        # Empty state chart
        fig = go.Figure()
        fig.add_annotation(
            text="No data to display<br>Try widening your JQL or adjusting filters",
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(
            title="Scope vs Completed",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            height=400
        )
        return fig
    
    # Prepare data
    dates = [point.date for point in daily_series]
    scope_values = [point.scope for point in daily_series]
    completed_values = [point.completed for point in daily_series]
    
    # Create deltas for hover
    scope_deltas = [point.delta_scope for point in daily_series]
    completed_deltas = [point.delta_completed for point in daily_series]
    
    # Calculate target completion for each date (linear interpolation)
    total_days = (t1 - t0).days if t1 > t0 else 1
    target_values = []
    for point in daily_series:
        days_elapsed = (point.date - t0).days
        target = (days_elapsed / total_days) * max_scope
        target_values.append(max(0, min(target, max_scope)))  # Clamp between 0 and max_scope
    
    # Create figure
    fig = go.Figure()
    
    # Add scope trace
    fig.add_trace(go.Scatter(
        x=dates,
        y=scope_values,
        mode='lines',
        name='Scope',
        line=dict(color='#1f77b4', width=2),
        hovertemplate='<b>%{fullData.name}</b><br>' +
                      'Date: %{x}<br>' +
                      'Value: %{y:.1f}<br>' +
                      'Δ: %{customdata:.1f}<br>' +
                      '<extra></extra>',
        customdata=scope_deltas
    ))
    
    # Add completed trace
    fig.add_trace(go.Scatter(
        x=dates,
        y=completed_values,
        mode='lines',
        name='Completed',
        line=dict(color='#ff7f0e', width=2),
        hovertemplate='<b>%{fullData.name}</b><br>' +
                      'Date: %{x}<br>' +
                      'Value: %{y:.1f}<br>' +
                      'Target: %{text:.1f}<br>' +
                      'Δ: %{customdata:.1f}<br>' +
                      '<extra></extra>',
        customdata=completed_deltas,
        text=target_values
    ))
    
    # Add ideal schedule line (from 0 at start to max_scope at end)
    fig.add_trace(go.Scatter(
        x=[t0, t1],
        y=[0, max_scope],
        mode='lines',
        name='Ideal Schedule',
        line=dict(color='#d62728', width=2, dash='dash'),
        hovertemplate='<b>%{fullData.name}</b><br>' +
                      'Date: %{x}<br>' +
                      'Target: %{y:.1f} points<br>' +
                      '<extra></extra>'
    ))
    
    # Update layout with strict axis locks
    fig.update_layout(
        title="Scope vs Completed",
        xaxis=dict(
            title="Date",
            type="date",
            range=[t0, t1],
            fixedrange=True,
            showspikes=True,
            spikemode="across",
            spikesnap="cursor"
        ),
        yaxis=dict(
            title="Story Points",
            range=[0, max_scope * 1.05],  # Add 5% padding at top
            fixedrange=True,
            showgrid=True
        ),
        hovermode="x unified",
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor="rgba(255,255,255,0.8)"
        ),
        height=500,
        showlegend=True
    )
    
    return fig


def format_number(value: float, precision: int = 1) -> str:
    """Format numbers with appropriate precision."""
    if value >= 1000:
        return f"{value/1000:.1f}k"
    elif value >= 100:
        return f"{value:.0f}"
    else:
        return f"{value:.{precision}f}"


def render_kpi_cards(results: ComputeResults):
    """Render the 4-up KPI cards."""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Max Scope",
            format_number(results.max_scope),
            help=f"Total story points at t1: {results.max_scope:.1f}"
        )
    
    with col2:
        st.metric(
            "Completed @ t1",
            format_number(results.completed_at_t1),
            help=f"Completed story points at t1: {results.completed_at_t1:.1f}"
        )
    
    with col3:
        st.metric(
            "% Complete",
            f"{results.percent_complete:.0f}%",
            help=f"Completion percentage: {results.percent_complete:.2f}%"
        )
    
    with col4:
        st.metric(
            "Included Issues",
            str(results.included_issues_count),
            help=f"Issues included after filtering: {results.included_issues_count}"
        )


def render_sidebar_controls(config: AppConfig, catalogs: FieldCatalogs) -> AppConfig:
    """Render all sidebar controls and return updated config."""
    st.sidebar.title("Controls")
    
    # Data Source section
    with st.sidebar.expander("📊 Data Source", expanded=True):
        jql = st.text_area(
            "JQL Query",
            value=config.jql,
            key="ctl_jql",
            placeholder="project = ABC AND issuetype in (Story, Bug, Task)",
            help="Jira Query Language to fetch issues"
        )
        
        timezone = st.selectbox(
            "Timezone",
            ["America/Toronto", "America/New_York", "America/Los_Angeles", "UTC", "Europe/London"],
            index=0,
            key="ctl_tz",
            help="Timezone for date parsing"
        )
        
        cache_raw = st.checkbox(
            "Cache raw results",
            value=config.cache_raw,
            key="ctl_cache",
            help="Speeds up filtering and recomputation"
        )
        
        # Combine common target statuses with actual statuses from data
        common_targets = ["Done Dev", "Done", "Closed", "Resolved"]
        available_statuses = list(catalogs.statuses) if catalogs.statuses else []
        # Add common targets that aren't already in the list
        all_status_options = common_targets + [s for s in available_statuses if s not in common_targets]
        
        target_status = st.selectbox(
            "Target Status for Completion",
            options=all_status_options,
            index=all_status_options.index(config.target_status) if config.target_status in all_status_options else 0,
            key="ctl_target_status",
            help="Track completion when issues first transition to this status"
        )
        
        fetch_clicked = st.button("🔄 Fetch / Refresh", key="btn_fetch", type="primary")
        
        if "fetch_error" in st.session_state and st.session_state.fetch_error:
            st.error(st.session_state.fetch_error)
    
    # Domain section
    with st.sidebar.expander("📅 Domain", expanded=True):
        t0_override = st.date_input(
            "Override Start (t0)",
            value=config.t0_override,
            key="ctl_t0_override",
            help="Override automatic start date detection"
        )
        
        t1_override = st.date_input(
            "Override End (t1)",
            value=config.t1_override,
            key="ctl_t1_override",
            help="Override automatic end date detection (default: Nov 11, 2025)"
        )
        
        t1_fallback = st.radio(
            "End (t1) fallback when no Due dates",
            ["Max Done", "Max Created", "Today"],
            index=0,
            key="ctl_t1_fallback",
            help="What to use as end date when no due dates exist and no override is set"
        )
        
        done_statuses = st.multiselect(
            "Done statuses",
            options=catalogs.statuses,
            default=config.done_statuses or [s for s in catalogs.statuses if any(word in s.lower() for word in ["done", "closed", "resolved"])],
            key="ctl_done_statuses",
            help="First entry into any of these counts as completion"
        )
        
        removed_statuses = st.multiselect(
            "Removed statuses (optional)",
            options=catalogs.statuses,
            default=config.removed_statuses,
            key="ctl_removed_statuses",
            help="Issues transitioning to these are considered removed from scope"
        )
        
        subtract_removed = st.checkbox(
            "Subtract when removed from scope",
            value=config.subtract_removed,
            key="ctl_subtract_removed",
            help="Subtract story points when issues move to removed statuses"
        )
    
    # Filters section
    with st.sidebar.expander("🔍 Filters", expanded=False):
        exclude_zombie = st.checkbox(
            'Exclude Resolution = "Zombie"',
            value=config.exclude_zombie,
            key="ctl_exclude_zombie",
            help="Exclude issues with zombie resolution"
        )
        
        drop_missing_created = st.checkbox(
            "Drop issues missing Created",
            value=config.drop_missing_created,
            key="ctl_drop_missing_created",
            help="Exclude issues without created date"
        )
        
        drop_missing_done = st.checkbox(
            "Drop issues missing Done transition",
            value=config.drop_missing_done,
            key="ctl_drop_missing_done",
            help="Exclude issues that never transitioned to done"
        )
        
        exclude_keys_text = st.text_area(
            "Exclude Issue Keys",
            value=", ".join(config.exclude_keys),
            key="ctl_exclude_keys",
            placeholder="ABC-123, ABC-456, ...",
            help="Comma-separated list of issue keys to exclude"
        )
        exclude_keys = [key.strip() for key in exclude_keys_text.split(",") if key.strip()]
        
        labels_filter = st.multiselect(
            "Labels",
            options=catalogs.labels,
            default=config.labels_filter,
            key="ctl_labels_filter",
            help="Include only issues with these labels"
        )
        
        components_filter = st.multiselect(
            "Components",
            options=catalogs.components,
            default=config.components_filter,
            key="ctl_components_filter",
            help="Include only issues with these components"
        )
        
        epics_filter = st.multiselect(
            "Epics",
            options=catalogs.epics,
            default=config.epics_filter,
            key="ctl_epics_filter",
            help="Include only issues from these epics"
        )
        
        assignees_filter = st.multiselect(
            "Assignees",
            options=catalogs.assignees,
            default=config.assignees_filter,
            key="ctl_assignees_filter",
            help="Include only issues assigned to these users"
        )
        
        include_subtasks = st.checkbox(
            "Include sub-tasks",
            value=config.include_subtasks,
            key="ctl_include_subtasks",
            help="Include sub-task issue types in analysis"
        )
    
    # Actions section
    with st.sidebar.expander("⚡ Actions", expanded=True):
        apply_clicked = st.button("✅ Apply Filters & Recompute", key="btn_apply", type="primary")
        reset_clicked = st.button("🔄 Reset Filters", key="btn_reset")
        
        with st.expander("Advanced"):
            show_intermediate = st.checkbox(
                "Show intermediate tables",
                value=config.show_intermediate,
                key="ctl_show_intermediate",
                help="Show transition and removal detection tables"
            )
            
            show_validation = st.checkbox(
                "Show validation report",
                value=config.show_validation,
                key="ctl_show_validation",
                help="Show detailed validation metrics and warnings"
            )
    
    # Update config
    new_config = AppConfig(
        jql=jql,
        timezone=timezone,
        cache_raw=cache_raw,
        t0_override=t0_override if t0_override else None,
        t1_override=t1_override if t1_override else None,
        t1_fallback=t1_fallback,
        target_status=target_status,
        done_statuses=done_statuses,
        removed_statuses=removed_statuses,
        subtract_removed=subtract_removed,
        exclude_zombie=exclude_zombie,
        drop_missing_created=drop_missing_created,
        drop_missing_done=drop_missing_done,
        exclude_keys=exclude_keys,
        labels_filter=labels_filter,
        components_filter=components_filter,
        epics_filter=epics_filter,
        assignees_filter=assignees_filter,
        include_subtasks=include_subtasks,
        show_intermediate=show_intermediate,
        show_validation=show_validation
    )
    
    return new_config, fetch_clicked, apply_clicked, reset_clicked


def create_download_button(df: pd.DataFrame, filename: str, label: str, key: str):
    """Create a download button for DataFrame."""
    if filename.endswith('.csv'):
        data = df.to_csv(index=False)
        mime = 'text/csv'
    else:  # json
        data = df.to_json(orient='records', indent=2)
        mime = 'application/json'
    
    st.download_button(
        label=label,
        data=data,
        file_name=filename,
        mime=mime,
        key=key
    )


def render_validation_report(results: ComputeResults):
    """Render validation report section."""
    st.subheader("📋 Validation Report")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Domain & Metrics:**")
        st.write(f"• t0: {results.t0}")
        st.write(f"• t1: {results.t1}")
        st.write(f"• Max Scope: {results.max_scope:.1f}")
        st.write(f"• Completed @ t1: {results.completed_at_t1:.1f}")
        st.write(f"• % Complete: {results.percent_complete:.2f}%")
    
    with col2:
        st.write("**Issue Counts:**")
        st.write(f"• Included: {results.included_issues_count}")
        st.write(f"• Excluded: {results.excluded_issues_count}")
        total = results.included_issues_count + results.excluded_issues_count
        st.write(f"• Total: {total}")
    
    if results.warnings:
        st.warning("**Warnings:**\n" + "\n".join(f"• {w}" for w in results.warnings))


def render_empty_state():
    """Render empty state with helpful suggestions."""
    st.info("🔍 **No issues found after applying filters**")
    
    st.write("**Common solutions:**")
    st.write("1. **Widen your JQL query** - Include more projects or issue types")
    st.write("2. **Turn off strict filters** - Disable 'Drop issues missing Created/Done'")
    st.write("3. **Check Zombie filter** - Disable 'Exclude Resolution = Zombie'")
    
    st.write("**Current filter summary:**")
    if "current_config" in st.session_state:
        config = st.session_state.current_config
        if config.exclude_keys:
            st.write(f"• Excluding {len(config.exclude_keys)} specific keys")
        if config.labels_filter:
            st.write(f"• Filtering by {len(config.labels_filter)} labels")
        if config.components_filter:
            st.write(f"• Filtering by {len(config.components_filter)} components")


def export_chart_png(fig: go.Figure, filename: str = "scope_completed_chart.png"):
    """Export chart as PNG - temporarily disabled due to browser issues."""
    st.info("📈 Chart PNG export temporarily disabled due to browser compatibility issues.")


def render_help_modal():
    """Render help modal with instructions."""
    if st.button("❓ Help", key="help_button"):
        st.session_state.show_help = True
    
    if st.session_state.get("show_help", False):
        with st.expander("📖 Help & Instructions", expanded=True):
            st.write("**Scope vs Completed Analysis**")
            st.write("This tool analyzes Jira issues to show scope growth vs completion over time.")
            
            st.write("**Key Concepts:**")
            st.write("• **Scope**: Cumulative story points of issues created by each date")
            st.write("• **Completed**: Cumulative story points of issues completed by each date")
            st.write("• **X-axis**: Locked to max Due date (or fallback)")
            st.write("• **Y-axis**: Locked to max Scope value")
            
            st.write("**Keyboard Shortcuts:**")
            st.write("• Press **?** to toggle this help")
            
            if st.button("Close Help"):
                st.session_state.show_help = False
