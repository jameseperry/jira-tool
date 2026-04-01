"""Component-related CLI commands."""

import click

from jira_tool.client import JiraError
from jira_tool.formatting import output_data


@click.group()
def component():
    """Commands for working with JIRA components."""
    pass


@component.command("list")
@click.argument("project")
@click.option("--json", "output_format", flag_value="json", help="Output as JSON")
@click.option("--yaml", "output_format", flag_value="yaml", help="Output as YAML")
@click.pass_obj
def component_list(ctx, project: str, output_format: str | None):
    """List all components in a project.

    \b
    Examples:
      # List all components in AISOLVE project
      jira-tool component list AISOLVE

      # Output as JSON
      jira-tool component list AISOLVE --json
    """
    try:
        components = ctx.client.get_project_components(project)
    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)

    if output_format:
        # JSON/YAML output
        simplified = [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "description": c.get("description", ""),
                "lead": c.get("lead", {}).get("displayName", "") if c.get("lead") else None,
                "assigneeType": c.get("assigneeType", ""),
            }
            for c in components
        ]
        output_data(simplified, output_format)
    else:
        # Table output
        if not components:
            click.echo(f"No components found in project {project}.")
            return

        click.echo(click.style(f"{'ID':<10} {'Name':<30} {'Lead':<25} {'Assignee Type'}", fg="cyan", bold=True))
        click.echo("─" * 95)

        for c in components:
            comp_id = c.get("id", "")[:9]
            name = c.get("name", "")[:29]
            lead = c.get("lead", {}).get("displayName", "-") if c.get("lead") else "-"
            lead = lead[:24]
            assignee_type = c.get("assigneeType", "")

            click.echo(f"{comp_id:<10} {name:<30} {lead:<25} {assignee_type}")

        click.echo("")
        click.echo(f"Total: {len(components)} components")


@component.command("create")
@click.argument("project")
@click.argument("name")
@click.option("--description", "-d", default=None, help="Component description")
@click.option("--lead", "-l", "lead_account_id", default=None, help="Component lead account ID")
@click.option(
    "--assignee-type",
    "-a",
    type=click.Choice(["PROJECT_DEFAULT", "COMPONENT_LEAD", "PROJECT_LEAD", "UNASSIGNED"], case_sensitive=False),
    default=None,
    help="Default assignee type for issues in this component"
)
@click.option("--json", "output_format", flag_value="json", help="Output as JSON")
@click.option("--yaml", "output_format", flag_value="yaml", help="Output as YAML")
@click.pass_obj
def component_create(
    ctx,
    project: str,
    name: str,
    description: str | None,
    lead_account_id: str | None,
    assignee_type: str | None,
    output_format: str | None
):
    """Create a new component in a project.

    \b
    Examples:
      # Create a simple component
      jira-tool component create AISOLVE "Backend API"

      # Create with description
      jira-tool component create AISOLVE "Frontend" -d "All UI-related tickets"

      # Create with component lead and assignee type
      jira-tool component create AISOLVE "DevOps" -l 123abc -a COMPONENT_LEAD
    """
    # Check global dry-run flag
    if ctx.dry_run:
        click.echo(click.style("DRY RUN - No changes will be made", fg="yellow", bold=True))
        click.echo(f"\nWould create component in project {project}:")
        click.echo(f"  Name: {name}")
        if description:
            click.echo(f"  Description: {description}")
        if lead_account_id:
            click.echo(f"  Lead: {lead_account_id}")
        if assignee_type:
            click.echo(f"  Assignee Type: {assignee_type}")
        return

    try:
        result = ctx.client.create_component(
            project_key=project,
            name=name,
            description=description,
            lead_account_id=lead_account_id,
            assignee_type=assignee_type,
        )
    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)

    if output_format:
        output_data(result, output_format)
    else:
        comp_id = result.get("id", "?")
        comp_name = result.get("name", "?")
        click.echo(click.style(f"✓ Created component: {comp_name} (ID: {comp_id})", fg="green"))
