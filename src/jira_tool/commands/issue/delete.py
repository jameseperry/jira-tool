"""Issue delete subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
)


@issue.command("delete")
@click.argument("issue_key")
@click.option(
    "--delete-subtasks", is_flag=True, default=False,
    help="Also delete subtasks. Without this, deletion fails if subtasks exist."
)
@click.option(
    "--force", "-f", is_flag=True, default=False,
    help="Skip confirmation prompt"
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be deleted without actually deleting"
)
@format_options
@click.pass_obj
@handle_api_errors
def issue_delete(
    ctx,
    issue_key: str,
    delete_subtasks: bool,
    force: bool,
    dry_run: bool,
    output_format: str,
):
    """Delete a JIRA issue.
    
    WARNING: This action is irreversible. The issue and all its data will be
    permanently deleted.
    
    \b
    Examples:
      # Delete an issue (will prompt for confirmation)
      jira-tool issue delete PROJ-123
      
      # Delete without confirmation
      jira-tool issue delete PROJ-123 --force
      
      # Delete issue and all its subtasks
      jira-tool issue delete PROJ-123 --delete-subtasks
      
      # Dry-run to see what would be deleted
      jira-tool issue delete PROJ-123 --dry-run
    """
    # Fetch issue details first to show what will be deleted
    issue_data = ctx.client.get_issue(issue_key)
    issue_summary = issue_data.get("fields", {}).get("summary", "")
    issue_type = issue_data.get("fields", {}).get("issuetype", {}).get("name", "")
    
    # Check for subtasks
    subtasks = issue_data.get("fields", {}).get("subtasks", [])
    has_subtasks = len(subtasks) > 0
    
    # Build deletion info
    deletion_info = {
        "issue": issue_key,
        "summary": issue_summary,
        "type": issue_type,
    }
    
    if has_subtasks:
        deletion_info["subtasks"] = [st.get("key", "") for st in subtasks]
        deletion_info["subtask_count"] = len(subtasks)
        deletion_info["delete_subtasks"] = delete_subtasks
    
    if dry_run:
        click.echo(click.style("DRY RUN - No issue will be deleted", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Would delete:", fg="cyan", bold=True), err=True)
        output_data(deletion_info, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        if has_subtasks and not delete_subtasks:
            click.echo(click.style(
                f"⚠ Warning: Issue has {len(subtasks)} subtask(s). "
                "Deletion would fail without --delete-subtasks flag.",
                fg="yellow"
            ), err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would delete issue: {issue_key}", fg="green", bold=True))
        return
    
    # Show what will be deleted and prompt for confirmation
    if not force:
        click.echo(click.style("About to delete:", fg="red", bold=True), err=True)
        click.echo(f"  Issue: {issue_key}", err=True)
        click.echo(f"  Summary: {issue_summary}", err=True)
        click.echo(f"  Type: {issue_type}", err=True)
        
        if has_subtasks:
            click.echo(f"  Subtasks: {len(subtasks)}", err=True)
            for st in subtasks[:5]:  # Show first 5
                click.echo(f"    - {st.get('key', '')}: {st.get('fields', {}).get('summary', '')}", err=True)
            if len(subtasks) > 5:
                click.echo(f"    ... and {len(subtasks) - 5} more", err=True)
            
            if delete_subtasks:
                click.echo(click.style("  ⚠ Subtasks WILL be deleted", fg="yellow"), err=True)
            else:
                click.echo(click.style(
                    "  ⚠ Deletion will FAIL - use --delete-subtasks to delete subtasks too",
                    fg="yellow"
                ), err=True)
        
        click.echo("", err=True)
        click.echo(click.style("This action is IRREVERSIBLE!", fg="red", bold=True), err=True)
        
        if not click.confirm("Are you sure you want to delete this issue?"):
            click.echo("Cancelled.", err=True)
            return
    
    # Actually delete the issue
    ctx.client.delete_issue(issue_key, delete_subtasks=delete_subtasks)
    
    if output_format == "text":
        click.echo(click.style(f"✓ Deleted issue: {issue_key}", fg="green", bold=True))
        if has_subtasks and delete_subtasks:
            click.echo(f"  Also deleted {len(subtasks)} subtask(s)")
    else:
        output = {
            "key": issue_key,
            "deleted": True,
        }
        if has_subtasks and delete_subtasks:
            output["subtasks_deleted"] = [st.get("key", "") for st in subtasks]
        output_data(output, output_format)
