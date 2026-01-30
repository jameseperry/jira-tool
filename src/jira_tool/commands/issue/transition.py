"""Issue transition subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
)


@issue.command("transition")
@click.argument("issue_key")
@click.argument("status", required=False)
@click.option(
    "--show", "-s", "list_transitions", is_flag=True, default=False,
    help="Show available transitions for the issue"
)
@click.option(
    "--comment", "-c", default=None,
    help="Add a comment with the transition"
)
@click.option(
    "--resolution", default=None,
    help="Set resolution (for transitions that require it, e.g., 'Done')"
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be done without actually transitioning"
)
@format_options
@click.pass_obj
@handle_api_errors
def issue_transition(
    ctx,
    issue_key: str,
    status: str | None,
    list_transitions: bool,
    comment: str | None,
    resolution: str | None,
    dry_run: bool,
    output_format: str,
):
    """Transition an issue to a new status.
    
    Use --show to see available transitions for an issue. The STATUS argument
    can be the transition name or target status name (case-insensitive, partial match).
    
    \b
    Examples:
      # Show available transitions
      jira-tool issue transition PROJ-123 --show
      
      # Transition to "In Progress"
      jira-tool issue transition PROJ-123 "In Progress"
      
      # Partial match works too
      jira-tool issue transition PROJ-123 progress
      
      # Add a comment with the transition
      jira-tool issue transition PROJ-123 Done -c "Fixed in latest commit"
      
      # Set resolution when closing
      jira-tool issue transition PROJ-123 Done --resolution Fixed
      
      # Dry-run to see what would happen
      jira-tool issue transition PROJ-123 Done --dry-run
    """
    # Get available transitions
    transitions = ctx.client.get_transitions(issue_key)
    
    if list_transitions:
        # Format transitions for display
        if output_format == "text":
            click.echo(click.style(f"Available transitions for {issue_key}:", fg="cyan", bold=True))
            click.echo("")
            for t in transitions:
                name = t.get("name", "")
                target = t.get("to", {}).get("name", "")
                tid = t.get("id", "")
                click.echo(f"  • {name}")
                click.echo(f"      → {target} (id: {tid})")
            if not transitions:
                click.echo("  No transitions available")
        else:
            simplified = [
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "to_status": t.get("to", {}).get("name"),
                    "to_status_id": t.get("to", {}).get("id"),
                }
                for t in transitions
            ]
            output_data(simplified, output_format)
        return
    
    # STATUS is required if not listing
    if not status:
        raise click.UsageError(
            "STATUS is required. Use --show to see available transitions."
        )
    
    # Find matching transition (case-insensitive partial match)
    status_lower = status.lower()
    matching = []
    for t in transitions:
        t_name = t.get("name", "").lower()
        t_to = t.get("to", {}).get("name", "").lower()
        if status_lower in t_name or status_lower in t_to:
            matching.append(t)
    
    if not matching:
        available = [f"{t.get('name')} → {t.get('to', {}).get('name')}" for t in transitions]
        raise click.UsageError(
            f"No transition matching '{status}' found.\n"
            f"Available transitions: {', '.join(available) or 'none'}"
        )
    
    if len(matching) > 1:
        options = [f"{t.get('name')} → {t.get('to', {}).get('name')}" for t in matching]
        raise click.UsageError(
            f"Ambiguous status '{status}' matches multiple transitions:\n"
            f"  {', '.join(options)}\n"
            "Please be more specific."
        )
    
    transition = matching[0]
    transition_id = transition.get("id")
    transition_name = transition.get("name")
    target_status = transition.get("to", {}).get("name")
    
    # Get current issue info for display
    issue_data = ctx.client.get_issue(issue_key)
    current_status = issue_data.get("fields", {}).get("status", {}).get("name", "")
    issue_summary = issue_data.get("fields", {}).get("summary", "")
    
    # Build payload preview
    payload = {
        "issue": issue_key,
        "summary": issue_summary,
        "current_status": current_status,
        "transition": transition_name,
        "new_status": target_status,
    }
    
    if comment:
        payload["comment"] = comment
    if resolution:
        payload["resolution"] = resolution
    
    # Build fields dict for API call
    fields = None
    if resolution:
        fields = {"resolution": {"name": resolution}}
    
    if dry_run:
        click.echo(click.style("DRY RUN - No transition will be performed", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Would transition:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would transition {issue_key}: {current_status} → {target_status}", fg="green", bold=True))
        return
    
    # Perform the transition
    ctx.client.transition_issue(
        issue_key=issue_key,
        transition_id=transition_id,
        comment=comment,
        fields=fields,
    )
    
    if output_format == "text":
        click.echo(click.style(f"✓ Transitioned {issue_key}: {current_status} → {target_status}", fg="green", bold=True))
        if comment:
            click.echo(f"  Comment added")
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  URL: {browse_url}")
    else:
        output = {
            "key": issue_key,
            "transitioned": True,
            "from_status": current_status,
            "to_status": target_status,
        }
        if comment:
            output["comment_added"] = True
        output_data(output, output_format)
