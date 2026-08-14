"""
github_agent -> GitHub REST: repos, languages, commit cadence, READMEs; read real source

This is what makes GitHub-grounded questions possible — question_planner
can't cite "the retry loop in llm_client.py" unless this agent actually
fetched that file's content, not just the repo's existence.

Caching: unauthenticated GitHub REST is 60 req/hr (see config note in
SETTINGS.github_token). We cache raw responses to output/prep/.github_cache/
so re-running the prep phase during dev doesn't burn the quota — "cache
hard" per the stack table.
"""
import hashlib
import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path("output/prep/.github_cache")
API_BASE = "https://api.github.com"


def _headers(token: str) -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _cached_get(url: str, token: str) -> dict | list:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(url.encode()).hexdigest()[:16]
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise RuntimeError(
            f"GitHub rate limit hit on {url}. Set GITHUB_TOKEN in .env "
            "(free PAT, no scopes needed for public repos) to raise the "
            "limit from 60/hr to 5,000/hr."
        )
    resp.raise_for_status()
    data = resp.json()
    cache_file.write_text(json.dumps(data))
    return data


def _extract_username(github_url: str) -> str:
    return github_url.rstrip("/").split("/")[-1]


def fetch_github_profile(github_url: str, token: str = "", max_repos: int = 6,
                          max_files_per_repo: int = 3) -> dict:
    """
    Returns structured GitHub evidence:
    {
      "username": "",
      "repos": [
        {
          "name": "", "description": "", "language": "",
          "commit_count_sample": 0, "last_pushed": "",
          "readme_excerpt": "",
          "source_samples": [{"path": "", "excerpt": ""}]
        }
      ]
    }
    """
    username = _extract_username(github_url)
    repos_raw = _cached_get(f"{API_BASE}/users/{username}/repos?sort=updated&per_page=30", token)
    if isinstance(repos_raw, dict):  # error payload (e.g. user not found)
        return {"username": username, "repos": [], "error": repos_raw.get("message", "unknown error")}

    non_fork = [r for r in repos_raw if not r.get("fork")]
    top_repos = sorted(non_fork, key=lambda r: r.get("pushed_at", ""), reverse=True)[:max_repos]

    repos_out = []
    for repo in top_repos:
        repo_name = repo["name"]
        entry = {
            "name": repo_name,
            "description": repo.get("description") or "",
            "language": repo.get("language") or "",
            "last_pushed": repo.get("pushed_at", ""),
            "readme_excerpt": "",
            "commit_count_sample": 0,
            "source_samples": [],
        }

        # README
        try:
            readme = _cached_get(f"{API_BASE}/repos/{username}/{repo_name}/readme", token)
            if isinstance(readme, dict) and "content" in readme:
                import base64
                raw = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
                entry["readme_excerpt"] = raw[:800]
        except Exception:
            pass  # no README is fine, not every repo has one

        # Commit cadence sample (first page only — cheap, still shows real activity)
        try:
            commits = _cached_get(f"{API_BASE}/repos/{username}/{repo_name}/commits?per_page=30", token)
            if isinstance(commits, list):
                entry["commit_count_sample"] = len(commits)
        except Exception:
            pass

        # Read real source: pull the repo tree, grab a few non-trivial files
        try:
            contents = _cached_get(f"{API_BASE}/repos/{username}/{repo_name}/contents", token)
            if isinstance(contents, list):
                code_files = [
                    f for f in contents
                    if f["type"] == "file"
                    and f["name"].split(".")[-1] in {"py", "js", "ts", "jsx", "tsx", "java", "go"}
                ][:max_files_per_repo]
                for f in code_files:
                    file_data = _cached_get(f["url"], token)
                    if isinstance(file_data, dict) and "content" in file_data:
                        import base64
                        raw = base64.b64decode(file_data["content"]).decode("utf-8", errors="replace")
                        entry["source_samples"].append({"path": f["path"], "excerpt": raw[:600]})
        except Exception:
            pass

        repos_out.append(entry)
        time.sleep(0.2)  # be polite to unauthenticated rate limit

    return {"username": username, "repos": repos_out}


def fetch_github_from_resume(resume_json_path: str = "output/prep/resume.json",
                              output_path: str = "output/prep/github.json",
                              token: str = "") -> dict:
    resume = json.loads(Path(resume_json_path).read_text())
    github_url = resume.get("github_url", "")
    if not github_url:
        result = {"username": "", "repos": [], "error": "No GitHub URL found in parsed resume."}
    else:
        result = fetch_github_profile(github_url, token=token)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    from src.config import SETTINGS
    out = fetch_github_from_resume(token=SETTINGS.github_token)
    print(json.dumps(out, indent=2)[:2000])
