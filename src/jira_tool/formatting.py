"""Formatting functions for JIRA tool output."""

import csv
import io
import json
from typing import Any

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jira_tool.utils import normalize_priority


def output_data(data: Any, fmt: str) -> None:
    """Output data in the specified format."""
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    elif fmt == "yaml":
        click.echo(yaml.dump(data, default_flow_style=False, sort_keys=False))
    elif fmt == "text":
        # format_issue_text prints directly via Rich, returns empty string
        result = format_issue_text(data)
        if result:
            click.echo(result)


def format_issues_csv(issues: list[dict]) -> str:
    """Format a list of simplified issues as CSV."""
    if not issues:
        return ""
    
    # Define columns for CSV output
    columns = [
        ("key", "Key"),
        ("summary", "Summary"),
        ("status", "Status"),
        ("type", "Type"),
        ("priority", "Priority"),
        ("assignee", "Assignee"),
        ("reporter", "Reporter"),
        ("created", "Created"),
        ("updated", "Updated"),
        ("due_date", "Due Date"),
        ("components", "Components"),
        ("labels", "Labels"),
        ("fix_versions", "Fix Versions"),
        ("parent_key", "Parent"),
    ]
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([col[1] for col in columns])
    
    # Write data rows
    for issue in issues:
        row = []
        for field_name, _ in columns:
            if field_name == "parent_key":
                parent = issue.get("parent")
                value = parent.get("key") if parent else ""
            elif field_name in ("components", "labels", "fix_versions"):
                # Join lists with semicolons
                value = ";".join(issue.get(field_name, []) or [])
            elif field_name in ("created", "updated"):
                # Just the date part
                full_date = issue.get(field_name, "")
                value = full_date[:10] if full_date else ""
            else:
                value = issue.get(field_name, "") or ""
            row.append(value)
        writer.writerow(row)
    
    return output.getvalue()


# Color mappings for table output
STATUS_COLORS = {
    "Done": "green",
    "Closed": "green",
    "Resolved": "green",
    "Discarded": "dim",
    "In Progress": "yellow",
    "Implementation": "yellow",
    "Review": "cyan",
    "In Review": "cyan",
    "Open": "white",
}

PRIORITY_COLORS = {
    "P1": "red bold",
    "P2": "yellow",
    "P3": "dim",
}

TYPE_COLORS = {
    "Bug": "red",
    "Epic": "magenta bold",
    "Story": "green",
    "Task": "blue",
    "Sub-task": "dim blue",
}

# Default columns for table display (in order)
DEFAULT_TABLE_COLUMNS = ["key", "status", "type", "priority", "assignee", "components", "summary"]

# Column definitions: field_name -> (header, style, no_wrap, ratio, max_width)
TABLE_COLUMN_DEFS = {
    "key": ("Key", "bold cyan", True, None, None),
    "status": ("Status", None, True, None, None),
    "type": ("Type", None, True, None, None),
    "priority": ("Priority", None, True, None, None),
    "assignee": ("Assignee", None, True, None, 18),
    "reporter": ("Reporter", None, True, None, 18),
    "components": ("Components", None, True, 1, 30),
    "labels": ("Labels", None, True, 1, 30),
    "fix_versions": ("Fix Versions", None, True, 1, 20),
    "summary": ("Summary", None, False, 3, 60),
    "description": ("Description", None, False, 2, 50),
    "created": ("Created", None, True, None, None),
    "updated": ("Updated", None, True, None, None),
    "due_date": ("Due", None, True, None, None),
    "project": ("Project", None, True, None, None),
    "parent": ("Parent", "cyan", True, None, None),
    "resolution": ("Resolution", None, True, None, None),
    "id": ("ID", "dim", True, None, None),
}


def _extract_field_value(issue: dict, field_name: str) -> str:
    """Extract a field value from a raw API issue for table display."""
    fields = issue.get("fields", {})
    
    if field_name == "key":
        return issue.get("key", "?")
    elif field_name == "id":
        return issue.get("id", "?")
    elif field_name == "status":
        return fields.get("status", {}).get("name", "?")
    elif field_name == "type":
        return fields.get("issuetype", {}).get("name", "?")
    elif field_name == "priority":
        priority_raw = fields.get("priority", {}).get("name") if fields.get("priority") else None
        return normalize_priority(priority_raw) or "-"
    elif field_name == "assignee":
        return fields.get("assignee", {}).get("displayName", "-") if fields.get("assignee") else "-"
    elif field_name == "reporter":
        return fields.get("reporter", {}).get("displayName", "-") if fields.get("reporter") else "-"
    elif field_name == "summary":
        return (fields.get("summary") or "").strip()
    elif field_name == "components":
        components = [c.get("name", "") for c in fields.get("components", [])]
        return ", ".join(components) if components else "-"
    elif field_name == "labels":
        labels = fields.get("labels", [])
        return ", ".join(labels) if labels else "-"
    elif field_name == "fix_versions":
        versions = [v.get("name", "") for v in fields.get("fixVersions", [])]
        return ", ".join(versions) if versions else "-"
    elif field_name == "created":
        val = fields.get("created", "")
        return val[:10] if val else "-"
    elif field_name == "updated":
        val = fields.get("updated", "")
        return val[:10] if val else "-"
    elif field_name == "due_date":
        return fields.get("duedate") or "-"
    elif field_name == "project":
        return fields.get("project", {}).get("key", "?")
    elif field_name == "parent":
        parent = fields.get("parent")
        return parent.get("key") if parent else "-"
    elif field_name == "resolution":
        res = fields.get("resolution")
        return res.get("name") if res else "-"
    else:
        return "-"


def _style_field_value(field_name: str, value: str) -> Text | str:
    """Apply color styling to a field value."""
    if field_name == "status":
        return Text(value, style=STATUS_COLORS.get(value, "white"))
    elif field_name == "priority":
        return Text(value, style=PRIORITY_COLORS.get(value, "white"))
    elif field_name == "type":
        return Text(value, style=TYPE_COLORS.get(value, "white"))
    elif field_name == "summary":
        # Escape brackets to prevent Rich markup interpretation
        return Text(value)
    else:
        return value


def format_issues_compact(issues: list[dict], selected_fields: set[str] | None = None) -> None:
    """Format issues as a rich table with dynamic columns.
    
    Args:
        issues: List of raw API issue dicts
        selected_fields: Set of field names to display, or None for defaults
    """
    console = Console()
    
    # Determine which columns to show (maintain a sensible order)
    if selected_fields is None:
        columns = DEFAULT_TABLE_COLUMNS
    else:
        # Keep columns in a logical order, only including selected ones
        all_ordered = ["key", "id", "status", "type", "priority", "resolution", 
                       "assignee", "reporter", "project", "parent", "components", 
                       "labels", "fix_versions", "created", "updated", "due_date", 
                       "summary", "description"]
        columns = [c for c in all_ordered if c in selected_fields]
        # Always ensure key is first if present
        if "key" in columns and columns[0] != "key":
            columns.remove("key")
            columns.insert(0, "key")
    
    # Build table
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    
    for col in columns:
        header, style, no_wrap, ratio, max_width = TABLE_COLUMN_DEFS.get(
            col, (col.title(), None, True, None, None)
        )
        kwargs = {"no_wrap": no_wrap}
        if style:
            kwargs["style"] = style
        if ratio:
            kwargs["ratio"] = ratio
        table.add_column(header, **kwargs)
    
    # Add rows
    for issue in issues:
        row_values = []
        for col in columns:
            value = _extract_field_value(issue, col)
            
            # Truncate if needed
            _, _, _, _, max_width = TABLE_COLUMN_DEFS.get(col, (None, None, None, None, None))
            if max_width and len(value) > max_width:
                value = value[:max_width - 3] + "..."
            
            # Apply styling
            styled = _style_field_value(col, value)
            row_values.append(styled)
        
        table.add_row(*row_values)
    
    console.print(table)


def format_issue_text(issue: dict) -> str:
    """Format a simplified issue as human-readable text using Rich."""
    console = Console()
    
    # Color mappings
    status_colors = {
        "Done": "green", "Closed": "green", "Resolved": "green",
        "Discarded": "dim",
        "In Progress": "yellow", "Implementation": "yellow",
        "Review": "cyan", "In Review": "cyan",
        "Open": "white",
    }
    priority_colors = {"P1": "red bold", "P2": "yellow", "P3": "dim"}
    type_colors = {
        "Bug": "red", "Epic": "magenta bold", "Story": "green",
        "Task": "blue", "Sub-task": "dim blue",
    }
    
    # Build the content
    lines = []
    
    # Summary as first line
    summary = (issue.get("summary") or "").strip()
    # Escape brackets to prevent Rich interpreting them as markup
    summary_escaped = summary.replace("[", "\\[").replace("]", "\\]")
    lines.append(f"[bold]{summary_escaped}[/bold]")
    lines.append("")
    
    # Status/Type/Priority line with colors
    meta_parts = []
    if issue.get("status"):
        status = issue["status"]
        color = status_colors.get(status, "white")
        meta_parts.append(f"[{color}]{status}[/{color}]")
    if issue.get("type"):
        issue_type = issue["type"]
        color = type_colors.get(issue_type, "white")
        meta_parts.append(f"[{color}]{issue_type}[/{color}]")
    if issue.get("priority"):
        priority = issue["priority"]
        color = priority_colors.get(priority, "white")
        meta_parts.append(f"[{color}]{priority}[/{color}]")
    if meta_parts:
        lines.append(" • ".join(meta_parts))
    
    # People
    if issue.get("assignee"):
        lines.append(f"[bold]Assignee:[/bold] {issue['assignee']}")
    if issue.get("reporter"):
        lines.append(f"[bold]Reporter:[/bold] {issue['reporter']}")
    
    # Project
    if issue.get("project"):
        lines.append(f"[bold]Project:[/bold] {issue['project']['name']} ({issue['project']['key']})")
    
    # Parent/Epic
    if issue.get("parent"):
        lines.append(f"[bold]Parent:[/bold] [cyan]{issue['parent']['key']}[/cyan] - {issue['parent']['summary']}")
    
    # Dates
    if issue.get("created"):
        lines.append(f"[bold]Created:[/bold] {issue['created'][:10]}")
    if issue.get("updated"):
        lines.append(f"[bold]Updated:[/bold] {issue['updated'][:10]}")
    if issue.get("due_date"):
        lines.append(f"[bold]Due:[/bold] {issue['due_date']}")
    
    # Time tracking
    if issue.get("time_tracking"):
        tt = issue["time_tracking"]
        tt_parts = []
        if tt.get("original_estimate"):
            tt_parts.append(f"[bold]Estimate:[/bold] {tt['original_estimate']}")
        if tt.get("time_spent"):
            tt_parts.append(f"[bold]Spent:[/bold] {tt['time_spent']}")
        if tt.get("remaining_estimate"):
            tt_parts.append(f"[bold]Remaining:[/bold] {tt['remaining_estimate']}")
        if tt_parts:
            lines.append("  ".join(tt_parts))
    
    # Labels & Components
    if issue.get("labels"):
        lines.append(f"[bold]Labels:[/bold] {', '.join(issue['labels'])}")
    if issue.get("components"):
        lines.append(f"[bold]Components:[/bold] {', '.join(issue['components'])}")
    if issue.get("fix_versions"):
        lines.append(f"[bold]Fix Versions:[/bold] {', '.join(issue['fix_versions'])}")
    
    # Description
    if issue.get("description"):
        lines.append("")
        lines.append("[bold]Description:[/bold]")
        # Escape any Rich markup in description
        for desc_line in issue["description"].split("\n"):
            # Escape brackets to prevent Rich interpreting them as markup
            escaped = desc_line.replace("[", "\\[").replace("]", "\\]")
            lines.append(f"  {escaped}")
    
    # Subtasks
    if issue.get("subtasks"):
        lines.append("")
        lines.append("[bold]Subtasks:[/bold]")
        for st in issue["subtasks"]:
            if st["status"] in ("Done", "Closed", "Resolved"):
                indicator = "[green]✓[/green]"
            else:
                indicator = "○"
            lines.append(f"  {indicator} [cyan]{st['key']}[/cyan]: {st['summary']} [{st['status']}]")
    
    # Links
    if issue.get("links"):
        lines.append("")
        lines.append("[bold]Links:[/bold]")
        for link in issue["links"]:
            lines.append(f"  {link['type']} ({link['direction']}): [cyan]{link['key']}[/cyan] - {link['summary']}")
    
    # Children (epic children, etc.)
    if issue.get("children"):
        lines.append("")
        lines.append("[bold]Children:[/bold]")
        for child in issue["children"]:
            status = child.get("status", "?")
            if status in ("Done", "Closed", "Resolved"):
                indicator = "[green]✓[/green]"
            else:
                indicator = "○"
            child_type = child.get("type", "")
            lines.append(f"  {indicator} [cyan]{child['key']}[/cyan]: {child['summary']} [{child_type}] [{status}]")
    
    # Comments
    if issue.get("comments"):
        lines.append("")
        lines.append("[bold]Comments:[/bold]")
        for comment in issue["comments"]:
            author = comment.get("author", "Unknown")
            created = comment.get("created", "")[:10] if comment.get("created") else ""
            lines.append("")
            lines.append(f"  [bold]{author}[/bold] [dim]({created})[/dim]")
            body = comment.get("body", "")
            if body:
                for body_line in body.split("\n"):
                    # Escape brackets in comment body
                    escaped = body_line.replace("[", "\\[").replace("]", "\\]")
                    lines.append(f"    {escaped}")
    
    content = "\n".join(lines)
    
    # Create panel with issue key as title
    panel = Panel(content, title=f"[bold cyan]{issue['key']}[/bold cyan]", title_align="left", border_style="dim")
    
    # Print directly to console and return empty string
    # (since output_data expects a string but we're using Rich)
    console.print(panel)
    return ""
