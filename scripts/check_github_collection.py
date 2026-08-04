"""Collect configured repository history and print a non-sensitive summary."""

from app import create_app
from app.clients.github import GitHubAPIError, GitHubClient
from app.services.github_history import GitHubHistoryCollector


def main() -> None:
    app = create_app()
    try:
        with GitHubClient.from_config(app.config) as client:
            history = GitHubHistoryCollector(client).collect()
    except (GitHubAPIError, ValueError) as exc:
        raise SystemExit(f"GitHub collection failed: {exc}") from exc

    print(f"repository={history.repository.full_name}")
    print(f"branches={len(history.branches)}")
    print(f"issues={len(history.issues)}")
    print(f"pull_requests={len(history.pull_requests)}")
    print(f"commits={len(history.commits)}")


if __name__ == "__main__":
    main()
