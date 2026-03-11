#!/usr/bin/env python3
"""
Run `ps -ef`, filter for lines containing 'tomcat' (like `ps -ef | grep tomcat`),
parse the standard columns and write the matching processes to JSON.

The script excludes lines that contain 'grep' to mimic the usual shell pipeline.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_ps():
    try:
        proc = subprocess.run(["ps", "-ef"], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running ps: {e}", file=sys.stderr)
        return None
    return proc.stdout


def parse_ps_lines(ps_text):
    """Parse `ps -ef` output into a list of dicts.

    Each entry has the keys: UID, PID, PPID, C, STIME, TTY, TIME, CMD
    """
    if not ps_text:
        return []
    lines = ps_text.splitlines()
    if not lines:
        return []

    header = lines[0]
    entries = []
    for line in lines[1:]:
        low = line.lower()
        if "tomcat" not in low:
            continue
        # exclude the grep itself
        if "grep" in low:
            continue

        # split into 8 columns: UID PID PPID C STIME TTY TIME CMD
        # use maxsplit=7 so CMD can contain spaces
        parts = line.split(None, 7)
        # If the line is shorter than expected, skip it
        if len(parts) < 8:
            # pad CMD if missing
            while len(parts) < 8:
                parts.append("")

        uid, pid, ppid, c, stime, tty, time_field, cmd = parts[:8]
        entries.append({
            "UID": uid,
            "PID": pid,
            "PPID": ppid,
            "C": c,
            "STIME": stime,
            "TTY": tty,
            "TIME": time_field,
            "CMD": cmd,
        })

    return entries


def run_jstack_for_pid(pid: str, out_dir: Path):
    """Run jstack for pid and write to a file jstack_<pid>.txt in out_dir.

    Returns a tuple (success: bool, path_or_error: str)
    """
    # capture jstack output
    try:
        proc = subprocess.run(["jstack", pid], capture_output=True, text=True, check=True)
    except FileNotFoundError:
        return False, "jstack-not-found"
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else str(e)
        return False, err

    jtext = proc.stdout

    # parse into structured JSON (best-effort)
    jjson = parse_jstack_to_json(jtext)

    # Optionally write per-pid JSON file later (caller decides)
    return True, jjson


def parse_jstack_to_json(jtext: str):
    """Best-effort parsing of jstack output into JSON.

    Returns a dict: { 'raw': <full_text>, 'threads': [ {name, header, state, stack:list, extras:list}, ... ] }
    """
    result = {"raw": jtext, "threads": []}
    if not jtext:
        return result

    lines = jtext.splitlines()
    cur_block = []

    def flush_block(block):
        if not block:
            return
        header = block[0]
        thread = {"name": None, "header": header, "state": None, "stack": [], "extras": []}

        # Extract name from header if present: starts with '"name"'
        if header.startswith('"'):
            try:
                end_quote = header.find('"', 1)
                # find the second quote index properly (header starts with ")
                # actually name can contain quotes; simpler: split by '"' and take second element
                parts = header.split('"')
                if len(parts) >= 2:
                    thread["name"] = parts[1]
            except Exception:
                thread["name"] = None

        state = None
        stack = []
        extras = []
        for ln in block[1:]:
            stripped = ln.strip()
            if stripped.startswith("java.lang.Thread.State:"):
                state = stripped[len("java.lang.Thread.State:"):].strip()
            elif stripped.startswith("at ") or stripped.startswith("\tat "):
                # stack frame
                stack.append(stripped.lstrip('\t'))
            else:
                extras.append(ln)

        thread["state"] = state
        thread["stack"] = stack
        thread["extras"] = extras
        result["threads"].append(thread)

    for ln in lines:
        # thread header lines typically start with a double quote
        if ln.startswith('"'):
            # flush previous
            flush_block(cur_block)
            cur_block = [ln]
        else:
            # continuation of current block
            if cur_block:
                cur_block.append(ln)
            else:
                # global header or noise; ignore for now
                pass

    # flush final
    flush_block(cur_block)

    return result


def main():
    parser = argparse.ArgumentParser(description="Save `ps -ef | grep tomcat` results as JSON")
    parser.add_argument("-o", "--output", default="tomcat_processes.json",
                        help="Output JSON file (default: tomcat_processes.json)")
    parser.add_argument("--jstack-dir", default="jstacks",
                        help="Directory to write per-PID jstack outputs if --save-jstack-files is used (default: jstacks)")
    parser.add_argument("--no-jstack", action="store_true",
                        help="Do not run jstack for matched PIDs")
    parser.add_argument("--save-jstack-files", action="store_true",
                        help="Also save per-PID jstack JSON files into --jstack-dir (default: off)")
    args = parser.parse_args()

    ps_out = run_ps()
    if ps_out is None:
        sys.exit(1)

    entries = parse_ps_lines(ps_out)

    out_path = Path(args.output)
    jstack_dir = Path(args.jstack_dir)

    # For each entry, optionally run jstack and attach result path or error
    if not args.no_jstack:
        for e in entries:
            pid = e.get("PID")
            if not pid:
                e["jstack_saved"] = False
                e["jstack_info"] = "no-pid"
                continue

            success, info = run_jstack_for_pid(pid, jstack_dir)
            if success:
                # info is the parsed JSON dict
                e["jstack_saved"] = True
                e["jstack"] = info

                # optionally save per-pid JSON files
                if args.save_jstack_files:
                    try:
                        jstack_dir.mkdir(parents=True, exist_ok=True)
                        out_file = jstack_dir / f"jstack_{pid}.json"
                        with out_file.open("w", encoding="utf-8") as jf:
                            json.dump(info, jf, indent=2, ensure_ascii=False)
                        e["jstack_info"] = str(out_file)
                    except OSError as ex:
                        e["jstack_info"] = f"save-failed: {ex}"
            else:
                e["jstack_saved"] = False
                e["jstack_info"] = info

    else:
        for e in entries:
            e["jstack_saved"] = False
            e["jstack_info"] = "skipped"

    try:
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Failed to write {out_path}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {len(entries)} tomcat process(es) to {out_path}")


if __name__ == "__main__":
    main()
