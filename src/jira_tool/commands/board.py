"""Board-related CLI commands."""

import click

from jira_tool.client import JiraError
from jira_tool.formatting import output_data


@click.group()
def board():
    """Commands for working with JIRA boards."""
    pass


@board.command("list")
@click.option("--project", "-p", default=None, help="Filter by project key")
@click.option("--type", "-t", "board_type", type=click.Choice(["scrum", "kanban"], case_sensitive=False), default=None, help="Filter by board type")
@click.option("--name", "-n", default=None, help="Filter by board name (contains match)")
@click.option("--json", "output_format", flag_value="json", help="Output as JSON")
@click.option("--yaml", "output_format", flag_value="yaml", help="Output as YAML")
@click.pass_obj
def board_list(ctx, project: str | None, board_type: str | None, name: str | None, output_format: str | None):
    """List all boards.

    \b
    Examples:
      # List all boards
      jira-tool board list

      # List boards for a specific project
      jira-tool board list -p AISOLVE

      # List only scrum boards
      jira-tool board list -t scrum
    """
    try:
        boards = ctx.client.get_boards(
            project_key=project,
            board_type=board_type,
            name=name,
            max_results=100,
        )
    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)

    if output_format:
        # JSON/YAML output
        simplified = [
            {
                "id": b.get("id", ""),
                "name": b.get("name", ""),
                "type": b.get("type", ""),
                "location": b.get("location", {}).get("projectKey", ""),
            }
            for b in boards
        ]
        output_data(simplified, output_format)
    else:
        # Table output
        if not boards:
            click.echo("No boards found.")
            return

        click.echo(click.style(f"{'ID':<10} {'Type':<10} {'Project':<15} {'Name'}", fg="cyan", bold=True))
        click.echo("─" * 80)

        for b in boards:
            board_id = str(b.get("id", ""))[:9]
            board_type = b.get("type", "")[:9]
            project = b.get("location", {}).get("projectKey", "-")[:14]
            board_name = b.get("name", "")

            click.echo(f"{board_id:<10} {board_type:<10} {project:<15} {board_name}")

        click.echo("")
        click.echo(f"Total: {len(boards)} boards")


@board.command("get")
@click.argument("board_id")
@click.option("--with-config", is_flag=True, default=False, help="Include board configuration (columns, etc.)")
@click.option("--json", "output_format", flag_value="json", help="Output as JSON")
@click.option("--yaml", "output_format", flag_value="yaml", help="Output as YAML")
@click.pass_obj
def board_get(ctx, board_id: str, with_config: bool, output_format: str | None):
    """Get board details and optionally configuration.

    The configuration includes column mappings, filters, and other settings
    that can be used to recreate the board in another project.

    \b
    Examples:
      # Get basic board info
      jira-tool board get 123

      # Get board with full configuration
      jira-tool board get 123 --with-config

      # Export board config as YAML
      jira-tool board get 123 --with-config --yaml > board-config.yaml
    """
    try:
        board_info = ctx.client.get_board(board_id)

        # Get the filter to see the JQL
        filter_id = board_info.get("filter", {}).get("id")
        filter_info = None
        if filter_id:
            try:
                filter_info = ctx.client.get_filter(filter_id)
            except JiraError:
                pass  # Filter might not be accessible

        config = None
        if with_config:
            try:
                config = ctx.client.get_board_configuration(board_id)
            except JiraError as e:
                click.echo(click.style(f"Warning: Could not fetch board configuration: {e}", fg="yellow"), err=True)

    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)

    if output_format:
        # JSON/YAML output - full export
        result = {
            "id": board_info.get("id"),
            "name": board_info.get("name"),
            "type": board_info.get("type"),
            "project": board_info.get("location", {}).get("projectKey"),
            "filter": {
                "id": filter_id,
                "name": filter_info.get("name") if filter_info else None,
                "jql": filter_info.get("jql") if filter_info else None,
            } if filter_info else None,
        }

        if config:
            result["configuration"] = {
                "columns": [
                    {
                        "name": col.get("name"),
                        "statuses": [s.get("name") for s in col.get("statuses", [])]
                    }
                    for col in config.get("columnConfig", {}).get("columns", [])
                ],
                "estimation": config.get("estimation", {}).get("type"),
                "ranking": config.get("ranking", {}).get("rankCustomFieldId"),
            }

        output_data(result, output_format)
    else:
        # Human-readable output
        click.echo(click.style(f"\nBoard: {board_info.get('name')}", fg="cyan", bold=True))
        click.echo(f"ID: {board_info.get('id')}")
        click.echo(f"Type: {board_info.get('type')}")
        click.echo(f"Project: {board_info.get('location', {}).get('projectKey', 'N/A')}")

        if filter_info:
            click.echo(f"\nFilter: {filter_info.get('name')} (ID: {filter_id})")
            click.echo(f"JQL: {filter_info.get('jql')}")

        if config:
            click.echo(f"\nColumns:")
            columns = config.get("columnConfig", {}).get("columns", [])
            for col in columns:
                col_name = col.get("name", "Unnamed")
                statuses = [s.get("name", "Unknown") for s in col.get("statuses", []) if s.get("name")]
                if statuses:
                    click.echo(f"  • {col_name}: {', '.join(statuses)}")
                else:
                    click.echo(f"  • {col_name}: (no statuses)")

            estimation = config.get("estimation", {})
            if estimation:
                click.echo(f"\nEstimation: {estimation.get('type', 'None')}")

        click.echo("")


@board.command("create")
@click.argument("name")
@click.option("--type", "-t", "board_type", type=click.Choice(["scrum", "kanban"], case_sensitive=False), default="scrum", help="Board type (default: scrum)")
@click.option("--filter-id", "-f", type=int, default=None, help="Existing filter ID to use")
@click.option("--filter-jql", "-j", default=None, help="JQL query for new filter (creates filter automatically)")
@click.option("--filter-name", default=None, help="Name for the new filter (used with --filter-jql)")
@click.option("--json", "output_format", flag_value="json", help="Output as JSON")
@click.option("--yaml", "output_format", flag_value="yaml", help="Output as YAML")
@click.pass_obj
def board_create(
    ctx,
    name: str,
    board_type: str,
    filter_id: int | None,
    filter_jql: str | None,
    filter_name: str | None,
    output_format: str | None
):
    """Create a new board.

    You must provide either an existing filter ID or a JQL query to create a new filter.

    \b
    Examples:
      # Create board with existing filter
      jira-tool board create "My Board" --filter-id 12345

      # Create board with new filter from JQL
      jira-tool board create "AISOLVE Board" --filter-jql "project = AISOLVE" --filter-name "AISOLVE Filter"

      # Create kanban board
      jira-tool board create "Support Board" -t kanban --filter-jql "project = SUPPORT"
    """
    if not filter_id and not filter_jql:
        click.echo(click.style("Error: Must provide either --filter-id or --filter-jql", fg="red"), err=True)
        raise SystemExit(1)

    if filter_id and filter_jql:
        click.echo(click.style("Error: Cannot provide both --filter-id and --filter-jql", fg="red"), err=True)
        raise SystemExit(1)

    # Check global dry-run flag
    if ctx.dry_run:
        click.echo(click.style("DRY RUN - No changes will be made", fg="yellow", bold=True))
        click.echo(f"\nWould create {board_type} board: {name}")
        if filter_id:
            click.echo(f"  Using existing filter ID: {filter_id}")
        if filter_jql:
            click.echo(f"  Would create filter with JQL: {filter_jql}")
            if filter_name:
                click.echo(f"  Filter name: {filter_name}")
        return

    try:
        # Create filter if JQL was provided
        if filter_jql:
            if not filter_name:
                filter_name = f"Filter for {name}"

            click.echo(f"Creating filter: {filter_name}")
            filter_result = ctx.client.create_filter(
                name=filter_name,
                jql=filter_jql,
                description=f"Auto-created filter for board: {name}",
            )
            filter_id = filter_result.get("id")
            click.echo(f"Created filter ID: {filter_id}")

        # Create the board
        click.echo(f"Creating {board_type} board: {name}")
        result = ctx.client.create_board(
            name=name,
            board_type=board_type,
            filter_id=filter_id,
        )

    except JiraError as e:
        click.echo(click.style(e.format_error(), fg="red"), err=True)
        raise SystemExit(1)

    if output_format:
        output_data(result, output_format)
    else:
        board_id = result.get("id", "?")
        board_name = result.get("name", "?")
        click.echo(click.style(f"\n✓ Created board: {board_name} (ID: {board_id})", fg="green"))
        click.echo(f"Type: {board_type}")
        click.echo(f"Filter ID: {filter_id}")
