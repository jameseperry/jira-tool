"""Issue create subcommand."""

import json

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
)


@issue.command("create")
@click.option("--project", "-p", required=True, help="Project key (e.g., PROJ)")
@click.option("--summary", "-s", required=True, help="Issue summary/title")
@click.option("--type", "issue_type", default="Task", help="Issue type (default: Task)")
@click.option("--description", "-d", default=None, help="Issue description")
@click.option("--assignee", "-a", default=None, help="Assignee account ID or email")
@click.option("--priority", default=None, help="Priority name (e.g., 'P1: High')")
@click.option("--label", "labels", multiple=True, help="Label (can specify multiple)")
@click.option("--component", "components", multiple=True, help="Component name (can specify multiple)")
@click.option("--parent", default=None, help="Parent issue key (for sub-tasks or epic children)")
@click.option("--field", "extra_fields", multiple=True, help="Additional field in 'name=value' format. Field names are auto-translated to IDs.")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be created without actually creating it")
@format_options
@click.pass_obj
@handle_api_errors
def issue_create(
    ctx,
    project: str,
    summary: str,
    issue_type: str,
    description: str | None,
    assignee: str | None,
    priority: str | None,
    labels: tuple[str, ...],
    components: tuple[str, ...],
    parent: str | None,
    extra_fields: tuple[str, ...],
    dry_run: bool,
    output_format: str,
):
    """Create a new JIRA issue.
    
    \b
    Examples:
      # Create a simple task
      jira-tool issue create -p PROJ -s "Fix login bug"
      
      # Create a bug with description
      jira-tool issue create -p PROJ -s "Login fails" --type Bug -d "Users cannot log in"
      
      # Create issue with labels and components
      jira-tool issue create -p PROJ -s "New feature" --label backend --label api --component Backend
      
      # Create a sub-task under a parent
      jira-tool issue create -p PROJ -s "Sub-task" --type Sub-task --parent PROJ-123
      
      # Use custom fields by name (auto-translated to field IDs)
      jira-tool issue create -p PROJ -s "Bug" --type Bug \\
        --field "Severity=High" --field "Steps to Reproduce=1. Do X\\n2. Do Y"
      
      # Dry-run to see what would be created
      jira-tool issue create -p PROJ -s "Test" --dry-run
    """
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
    payload = {
        "project": project,
        "summary": summary,
        "type": issue_type,
    }
    
    if description:
        payload["description"] = description
    if assignee:
        payload["assignee"] = assignee
    if priority:
        payload["priority"] = priority
    if labels:
        payload["labels"] = list(labels)
    if components:
        payload["components"] = list(components)
    if parent:
        payload["parent"] = parent
    if parsed_extra_fields:
        payload["extra_fields"] = parsed_extra_fields
        payload["extra_fields_translated"] = translated_extra_fields
    
    if dry_run:
        # Show what would be created
        click.echo(click.style("DRY RUN - No issue will be created", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("API Payload:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        # Fake result for consistent output
        result = {
            "id": "00000",
            "key": f"{project}-XXXXX",
            "self": f"{ctx.client.base_url}/issue/00000",
        }
    else:
        # Actually create the issue
        result = ctx.client.create_issue(
            project_key=project,
            summary=summary,
            issue_type=issue_type,
            description=description,
            assignee=assignee,
            priority=priority,
            labels=list(labels) if labels else None,
            components=list(components) if components else None,
            parent=parent,
            extra_fields=translated_extra_fields,
        )
    
    # Extract key info from result
    issue_key = result.get("key", "")
    issue_id = result.get("id", "")
    issue_self = result.get("self", "")
    
    if output_format == "text":
        prefix = "[DRY RUN] " if dry_run else ""
        click.echo(click.style(f"✓ {prefix}Created issue: {issue_key}", fg="green", bold=True))
        
        # Build issue URL
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  URL: {browse_url}")
    else:
        # Return simplified response for JSON/YAML
        output = {
            "key": issue_key,
            "id": issue_id,
            "self": issue_self,
            "created": True,
        }
        output_data(output, output_format)
