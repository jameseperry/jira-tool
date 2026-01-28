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


def format_issues_compact(issues: list[dict]) -> None:
    """Format issues as a rich table."""
    console = Console()
    
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Priority", no_wrap=True)
    table.add_column("Assignee", no_wrap=True)
    table.add_column("Components", no_wrap=True, ratio=1)
    table.add_column("Summary", ratio=3)
    
    for issue in issues:
        fields = issue.get("fields", {})
        key = issue.get("key", "?")
        summary = (fields.get("summary") or "").strip()
        status = fields.get("status", {}).get("name", "?")
        issue_type = fields.get("issuetype", {}).get("name", "?")
        priority_raw = fields.get("priority", {}).get("name") if fields.get("priority") else None
        priority = normalize_priority(priority_raw) or "-"
        assignee = fields.get("assignee", {}).get("displayName", "-") if fields.get("assignee") else "-"
        components = [c.get("name", "") for c in fields.get("components", [])]
        components_str = ", ".join(components) if components else "-"
        
        # Truncate summary if too long
        max_summary = 60
        if len(summary) > max_summary:
            summary = summary[:max_summary - 3] + "..."
        
        # Truncate assignee name
        if len(assignee) > 18:
            assignee = assignee[:15] + "..."
        
        # Truncate components if too long
        if len(components_str) > 30:
            components_str = components_str[:27] + "..."
        
        # Color-code status
        status_colors = {
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
        status_text = Text(status, style=status_colors.get(status, "white"))
        
        # Color-code priority
        priority_colors = {
            "P1": "red bold",
            "P2": "yellow",
            "P3": "dim",
        }
        priority_text = Text(priority, style=priority_colors.get(priority, "white"))
        
        # Color-code issue type
        type_colors = {
            "Bug": "red",
            "Epic": "magenta bold",
            "Story": "green",
            "Task": "blue",
            "Sub-task": "dim blue",
        }
        type_text = Text(issue_type, style=type_colors.get(issue_type, "white"))
        
        # Use Text() for summary to prevent Rich from interpreting [brackets] as markup
        table.add_row(key, status_text, type_text, priority_text, assignee, components_str, Text(summary))
    
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
