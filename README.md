# jira-tool

A command-line interface for interacting with JIRA Cloud API.

## Features

- Fetch issue details with simplified, human-readable output
- Search issues using JQL or convenient filter options
- Multiple output formats: text (Rich tables/panels), JSON, YAML, CSV
- Color-coded status, priority, and issue types
- Automatic fetching of child issues for epics
- Comment viewing support

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/jira-tool.git
cd jira-tool

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .
```

## Configuration

Authentication is configured via environment variables:

```bash
export JIRA_BASE_URL="https://yourcompany.atlassian.net"
export JIRA_EMAIL="your.email@company.com"
export JIRA_API_TOKEN="your-api-token"
```

To generate an API token, visit: https://id.atlassian.com/manage-profile/security/api-tokens

You can also pass these as command-line options (`--base-url`, `--email`, `--token`), but environment variables are recommended.

### Optional

```bash
export JIRA_DEBUG=1  # Enable debug output on errors
```

## Usage

### Get Issue Details

Fetch one or more issues by key:

```bash
# Single issue
jira-tool issue get PROJ-123

# Multiple issues
jira-tool issue get PROJ-123 PROJ-124 PROJ-125

# Include comments
jira-tool issue get PROJ-123 --comments

# Output as JSON
jira-tool issue get PROJ-123 --json

# Output as YAML
jira-tool issue get PROJ-123 --yaml

# Raw API response (for debugging)
jira-tool issue get PROJ-123 --raw --include-custom-fields
```

### Search Issues

Search using convenient filter options:

```bash
# Find your open issues in a project
jira-tool issue search --project PROJ --assignee me

# Find issues by status
jira-tool issue search --project PROJ --status "In Progress"

# Find bugs updated in the last week
jira-tool issue search --type Bug --updated-after -7d

# Find high priority issues
jira-tool issue search --project PROJ --priority "P1: High"

# Full-text search
jira-tool issue search --text "memory leak" --project PROJ

# Combine multiple filters
jira-tool issue search \
  --project PROJ \
  --assignee me \
  --type Story \
  --status "In Progress" \
  --updated-after -30d

# Use raw JQL for complex queries
jira-tool issue search --jql "project = PROJ AND status = Open ORDER BY created DESC"
```

#### Search Filter Options

| Option | Description |
|--------|-------------|
| `--project`, `-p` | Project key |
| `--component`, `-c` | Component name (can specify multiple) |
| `--assignee`, `-a` | Assignee (use `me` for yourself, `unassigned` for none) |
| `--reporter` | Reporter (use `me` for yourself) |
| `--status`, `-s` | Status (can specify multiple) |
| `--type` | Issue type: Bug, Story, Task, Epic, Sub-task |
| `--priority` | Priority level |
| `--label` | Label (can specify multiple) |
| `--fix-version` | Fix version (can specify multiple) |
| `--parent` | Parent issue key (for epic children or subtasks) |
| `--created-after` | Created after date (YYYY-MM-DD or -7d for relative) |
| `--created-before` | Created before date |
| `--updated-after` | Updated after date |
| `--updated-before` | Updated before date |
| `--text`, `-q` | Full-text search |
| `--allow-closed` | Include Done/Closed issues (excluded by default) |
| `--order-by` | Sort order (default: `updated DESC`) |
| `--limit` | Maximum results (default: 50) |
| `--show-jql` | Print the generated JQL query |

### Get Child Issues

Fetch all children of an epic or parent issue:

```bash
jira-tool issue children PROJ-100

# Output as list of keys (for scripting)
jira-tool issue children PROJ-100 --list
```

### Output Formats

All commands support multiple output formats:

| Flag | Description |
|------|-------------|
| `--human` | Human-readable text with Rich formatting (default) |
| `--json` | JSON output |
| `--yaml` | YAML output |
| `--csv` | CSV output (best for search results) |
| `--list`, `-l` | Just issue keys, one per line (for scripting) |

### Scripting Examples

```bash
# Pipe issue keys to another command
jira-tool issue search -p PROJ -a me --list | xargs -I {} echo "Processing {}"

# Export search results to CSV
jira-tool issue search -p PROJ --updated-after -7d --csv > issues.csv

# Get issues as JSON for processing with jq
jira-tool issue search -p PROJ --json | jq '.[].key'
```

## Debug Mode

Enable debug mode for verbose error output including stack traces and raw API responses:

```bash
# Via environment variable
export JIRA_DEBUG=1
jira-tool issue get PROJ-123

# Via command-line flag
jira-tool --debug issue get PROJ-123
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/jira_tool
```

## License

MIT
