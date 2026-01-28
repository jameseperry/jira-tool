"""Issue edit subcommand."""

import json

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
)


@issue.command("edit")
@click.argument("issue_key")
@click.option("--summary", "-s", default=None, help="New issue summary/title")
@click.option("--description", "-d", default=None, help="New issue description")
@click.option("--assignee", "-a", default=None, help="New assignee (use '' to unassign)")
@click.option("--priority", default=None, help="New priority name")
@click.option("--label", "labels", multiple=True, help="Set labels (replaces existing, can specify multiple)")
@click.option("--component", "components", multiple=True, help="Set components (replaces existing, can specify multiple)")
@click.option("--field", "extra_fields", multiple=True, help="Additional field in 'name=value' format. Field names are auto-translated to IDs.")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be changed without actually updating")
@format_options
@click.pass_obj
@handle_api_errors
def issue_edit(
    ctx,
    issue_key: str,
    summary: str | None,
    description: str | None,
    assignee: str | None,
    priority: str | None,
    labels: tuple[str, ...],
    components: tuple[str, ...],
    extra_fields: tuple[str, ...],
    dry_run: bool,
    output_format: str,
):
    """Edit an existing JIRA issue.
    
    \b
    Examples:
      # Update summary
      jira-tool issue edit PROJ-123 -s "New title"
      
      # Update description
      jira-tool issue edit PROJ-123 -d "New description"
      
      # Change assignee
      jira-tool issue edit PROJ-123 -a user@example.com
      
      # Unassign issue
      jira-tool issue edit PROJ-123 -a ""
      
      # Update custom fields by name
      jira-tool issue edit PROJ-123 --field "Severity=Critical"
      
      # Multiple changes at once
      jira-tool issue edit PROJ-123 -s "New title" --priority "P1: High" --label urgent
      
      # Dry-run to see what would be changed
      jira-tool issue edit PROJ-123 -s "New title" --dry-run
    """
    # Check that at least one field is being changed
    has_changes = any([
        summary is not None,
        description is not None,
        assignee is not None,
        priority is not None,
        labels,
        components,
        extra_fields,
    ])
    
    if not has_changes:
        raise click.UsageError("No fields specified to update. Use --help to see available options.")
    
    # Parse extra fields from "name=value" format
    parsed_extra_fields = {}
    for field_spec in extra_fields:
        if "=" not in field_spec:
            raise click.UsageError(f"Invalid field format: '{field_spec}'. Use 'name=value' format.")
        name, value = field_spec.split("=", 1)
        name = name.strip()
        value = value.strip()
        
        # Try to parse as JSON for complex values, otherwise use as string
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            # Handle escaped newlines in string values
            parsed_value = value.replace("\\n", "\n")
        
        parsed_extra_fields[name] = parsed_value
    
    # Translate field names to IDs if we have extra fields
    translated_extra_fields = None
    if parsed_extra_fields:
        translated_extra_fields = ctx.client.translate_field_names(parsed_extra_fields)
    
    # Build the payload preview
    payload = {"issue": issue_key}
    
    if summary is not None:
        payload["summary"] = summary
    if description is not None:
        payload["description"] = description
    if assignee is not None:
        payload["assignee"] = assignee if assignee else "(unassign)"
    if priority is not None:
        payload["priority"] = priority
    if labels:
        payload["labels"] = list(labels)
    if components:
        payload["components"] = list(components)
    if parsed_extra_fields:
        payload["extra_fields"] = parsed_extra_fields
        payload["extra_fields_translated"] = translated_extra_fields
    
    if dry_run:
        # Show what would be changed
        click.echo(click.style("DRY RUN - No changes will be made", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Changes to apply:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would update issue: {issue_key}", fg="green", bold=True))
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  URL: {browse_url}")
    else:
        # Actually update the issue
        ctx.client.update_issue(
            issue_key=issue_key,
            summary=summary,
            description=description,
            assignee=assignee,
            priority=priority,
            labels=list(labels) if labels else None,
            components=list(components) if components else None,
            extra_fields=translated_extra_fields,
        )
        
        if output_format == "text":
            click.echo(click.style(f"✓ Updated issue: {issue_key}", fg="green", bold=True))
            if ctx.client.base_url:
                browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
                click.echo(f"  URL: {browse_url}")
        else:
            output = {
                "key": issue_key,
                "updated": True,
            }
            output_data(output, output_format)
