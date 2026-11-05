#!/usr/bin/env python3
"""Synchronize local main branch with both personal and Packt GitHub remotes.

Remotes:
  origin: https://github.com/kenhuangus/llm-design-patterns-hands-on.git
  packt:  https://github.com/PacktPublishing/LLM-Design-Patterns-Second-Edition.git
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REMOTES = {
    "origin": "https://github.com/kenhuangus/llm-design-patterns-hands-on.git",
    "packt": "https://github.com/PacktPublishing/LLM-Design-Patterns-Second-Edition.git",
}


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *args]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if check and res.returncode != 0:
        print(f"Error executing: {' '.join(cmd)}", file=sys.stderr)
        print(res.stderr or res.stdout, file=sys.stderr)
        sys.exit(res.returncode)
    return res


def main() -> None:
    print("=== Checking repository remotes ===")
    remotes_output = run_git("remote", "-v").stdout
    
    # Ensure both remotes are configured
    for name, url in REMOTES.items():
        if name not in remotes_output:
            print(f"Adding remote '{name}' -> {url}")
            run_git("remote", "add", name, url)
    
    # Configure dual push URLs on origin
    run_git("config", "--unset-all", "remote.origin.pushurl", check=False)
    run_git("remote", "set-url", "--add", "--push", "origin", REMOTES["origin"])
    run_git("remote", "set-url", "--add", "--push", "origin", REMOTES["packt"])
    
    # Configure dual push URLs on packt
    run_git("config", "--unset-all", "remote.packt.pushurl", check=False)
    run_git("remote", "set-url", "--add", "--push", "packt", REMOTES["packt"])
    run_git("remote", "set-url", "--add", "--push", "packt", REMOTES["origin"])
    
    # Fetch from both
    print("=== Fetching latest refs from both remotes ===")
    run_git("fetch", "origin")
    run_git("fetch", "packt")
    
    # Get local HEAD SHA
    local_sha = run_git("rev-parse", "HEAD").stdout.strip()
    branch = run_git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    print(f"Local current branch: {branch} ({local_sha[:7]})")
    
    if branch != "main":
        print(f"Warning: Not on main branch. Checking main branch SHA...")
        main_sha = run_git("rev-parse", "main").stdout.strip()
    else:
        main_sha = local_sha

    print(f"=== Pushing main to both remotes ===")
    for remote in ["origin", "packt"]:
        print(f"Pushing main to {remote} ({REMOTES[remote]})...")
        res = run_git("push", remote, "main")
        print(res.stdout.strip() or "Up-to-date")
    
    # Verify sync
    print("=== Verifying synchronization ===")
    origin_sha = run_git("rev-parse", "origin/main").stdout.strip()
    packt_sha = run_git("rev-parse", "packt/main").stdout.strip()
    
    print(f"  Local main:  {main_sha[:7]}")
    print(f"  origin/main: {origin_sha[:7]}")
    print(f"  packt/main:  {packt_sha[:7]}")
    
    if main_sha == origin_sha == packt_sha:
        print("\nSUCCESS: Both repositories are perfectly in sync on main!")
    else:
        print("\nERROR: Remotes are not matching local main!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
