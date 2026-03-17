#!/usr/bin/env python3
"""Detect and remove stale tmux sessions where all bot processes are dead."""
import argparse
import os
import subprocess
import sys


def cleanup_zombie_tmux_sessions(dry_run: bool = False) -> int:
    """Kill tmux sessions where all pane PIDs are dead.

    Returns count of sessions cleaned up.
    """
    try:
        result = subprocess.run(
            ["tmux", "ls", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        # No tmux server running or no sessions
        return 0
    except FileNotFoundError:
        # tmux not installed
        return 0

    sessions = [s for s in result.stdout.splitlines() if s.strip()]
    killed = 0

    for session in sessions:
        try:
            pane_result = subprocess.run(
                ["tmux", "list-panes", "-t", session, "-F", "#{pane_pid}"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            # Session may have disappeared between ls and list-panes; skip
            continue

        pids = [p.strip() for p in pane_result.stdout.splitlines() if p.strip()]
        if not pids:
            continue

        all_dead = True
        for pid_str in pids:
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            try:
                os.kill(pid, 0)
                # Process exists — session is alive
                all_dead = False
                break
            except ProcessLookupError:
                # PID does not exist — this pane is dead
                pass
            except PermissionError:
                # PID exists but we lack permission to signal it — still alive
                all_dead = False
                break

        if all_dead:
            if dry_run:
                print(f"[dry-run] zombie session: {session} (pids: {', '.join(pids)})")
            else:
                try:
                    subprocess.run(
                        ["tmux", "kill-session", "-t", session],
                        check=True,
                        capture_output=True,
                    )
                    print(f"Killed zombie tmux session: {session}")
                except subprocess.CalledProcessError as exc:
                    print(f"Warning: failed to kill session {session}: {exc}", file=sys.stderr)
                    continue
            killed += 1

    return killed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect and remove stale tmux sessions where all bot processes are dead."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List zombie sessions without killing them.",
    )
    args = parser.parse_args()

    count = cleanup_zombie_tmux_sessions(dry_run=args.dry_run)
    if count == 0:
        print("No zombie tmux sessions found.")
    elif args.dry_run:
        print(f"{count} zombie session(s) would be cleaned up.")
    else:
        print(f"Cleaned up {count} zombie tmux session(s).")


if __name__ == "__main__":
    main()
