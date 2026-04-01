"""Issue move commands."""

import click

from jira_tool.client import JiraError


@click.command("move")
@click.argument("issue_key")
@click.argument("target_project")
@click.option(
    "--map-component",
    "-c",
    "component_mappings",
    multiple=True,
    help='Map component names: "NewName=OldName". Can be specified multiple times.'
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview the move without making changes"
)
@click.pass_obj
def move(ctx, issue_key: str, target_project: str, component_mappings: tuple[str, ...], dry_run: bool):
    """Move an issue to a different project.

    When moving an issue, the issue key will change to match the target project.
    For example, moving PROJ-123 to NEWPROJ will result in a new key like NEWPROJ-456.

    Components can be mapped using --map-component flags. If an issue has components
    that don't exist in the target project, you must map them.

    \b
    Examples:
      # Simple move
      jira-tool issue move OLDPROJ-1 NEWPROJ

      # Move with component mapping
      jira-tool issue move OLDPROJ-1 NEWPROJ -c "API=Backend" -c "UI=Frontend"

      # Preview the move without executing
      jira-tool issue move OLDPROJ-1 NEWPROJ --dry-run
    """
    # Check global dry-run flag as well as local flag
    dry_run = dry_run or ctx.dry_run

    # Parse component mappings from "New=Old" format
    component_map = {}
    for mapping in component_mappings:
        if "=" not in mapping:
            click.echo(click.style(f"Invalid component mapping: '{mapping}'. Expected format: 'NewName=OldName'", fg="red"), err=True)
            raise SystemExit(1)
        new_name, old_name = mapping.split("=", 1)
        component_map[old_name.strip()] = new_name.strip()

    try:
        # Fetch the issue first to show current state
        issue = ctx.client.get_issue(issue_key, fields=["summary", "project", "components", "issuetype"])
        fields = issue.get("fields", {})

        current_project = fields.get("project", {}).get("key", "?")
        summary = fields.get("summary", "")
        issue_type = fields.get("issuetype", {}).get("name", "?")
        current_components = fields.get("components", [])
        current_component_names = [c.get("name", "") for c in current_components]

        # Show current state
        click.echo(click.style(f"\n{'='*60}", fg="cyan"))
        click.echo(click.style(f"Issue: {issue_key}", fg="cyan", bold=True))
        click.echo(f"Summary: {summary}")
        click.echo(f"Type: {issue_type}")
        click.echo(f"Current Project: {current_project}")
        click.echo(f"Target Project: {target_project}")

        if current_component_names:
            click.echo(f"Current Components: {', '.join(current_component_names)}")

            # Show component mapping
            if component_map:
                new_component_names = [component_map.get(c, c) for c in current_component_names]
                click.echo(f"New Components: {', '.join(new_component_names)}")
        else:
            click.echo("Current Components: None")

        click.echo(click.style(f"{'='*60}\n", fg="cyan"))

        if dry_run:
            click.echo(click.style("DRY RUN - No changes will be made", fg="yellow", bold=True))
            click.echo(f"\nWould move {issue_key} from {current_project} to {target_project}")
            if component_map:
                click.echo("\nComponent mappings:")
                for old, new in component_map.items():
                    click.echo(f"  {old} → {new}")
            return

        # Confirm the move
        if not click.confirm(f"\nMove {issue_key} to {target_project}?"):
            click.echo("Move cancelled.")
            return

        # Perform the move
        ctx.client.move_issue(issue_key, target_project, component_map if component_map else None)

        # Verify the move succeeded by re-fetching the issue
        click.echo("\nVerifying move...")
        updated_issue = ctx.client.get_issue(issue_key, fields=["project", "components"])
        new_project = updated_issue.get("fields", {}).get("project", {}).get("key", "")
        new_components = updated_issue.get("fields", {}).get("components", [])
        new_component_names = [c.get("name", "") for c in new_components]

        if new_project != target_project:
            click.echo(click.style(f"\n✗ Move failed - issue is still in {new_project}", fg="red"))
            click.echo(click.style(f"\nPossible reasons:", fg="yellow"))
            click.echo(f"  • Issue type '{issue_type}' may not exist in {target_project}")
            click.echo(f"  • Target project may have required fields that aren't set")
            click.echo(f"  • You may not have permission to create issues in {target_project}")
            click.echo(f"\nTry checking available issue types in {target_project}:")
            click.echo(f"  jira-tool field options {target_project} {issue_type}")
            raise SystemExit(1)

        # The issue key will have changed, but we don't know the new key
        # Note: JIRA API doesn't return the new key after a move
        click.echo(click.style(f"\n✓ Successfully moved {issue_key} to {target_project}", fg="green"))
        if new_component_names:
            click.echo(f"Components: {', '.join(new_component_names)}")
        click.echo(click.style(f"Note: The issue key has changed. Search for it in {target_project} to find the new key.", fg="yellow"))

    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)
