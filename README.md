# ps_grep_tomcat_to_json

Small utility to capture `ps -ef | grep tomcat` style results and collect Java thread dumps (via `jstack`) as JSON.

This project contains a single script: `ps_grep_tomcat_to_json.py` which:

- runs `ps -ef` and filters processes whose command line contains the word `tomcat` (case-insensitive)
- parses `ps` columns into structured JSON
- optionally runs `jstack <PID>` for each matched process and embeds a parsed thread dump into the main JSON output (no .txt files by default)
- optionally saves per-PID jstack JSON files when requested

## Requirements

- Linux / POSIX environment with `ps` available (tested on Linux)
- Python 3.6+
- `jstack` on PATH if you want thread dumps; jstack is part of JDK/bin

If `jstack` is not available or fails to attach, the JSON will record an error string for that PID instead of the embedded dump.

## Files

- `ps_grep_tomcat_to_json.py` — main script
- `jstacks/` — default directory used when saving per-PID jstack JSON files (created only when requested)

## Usage

Run the script from the project root. By default it writes `tomcat_processes.json` in the current directory and embeds parsed jstack JSON when `jstack` is available.

Default (embed jstack JSON into `tomcat_processes.json`):

```bash
python3 ps_grep_tomcat_to_json.py
```

Skip running `jstack` (only JSON with process info):

```bash
python3 ps_grep_tomcat_to_json.py --no-jstack
```

Save per-PID jstack JSON files in addition to embedding (writes files into `jstacks/` by default):

```bash
python3 ps_grep_tomcat_to_json.py --save-jstack-files --jstack-dir jstacks
```

Specify a custom JSON output path:

```bash
python3 ps_grep_tomcat_to_json.py -o /tmp/out.json
```

## CLI flags

- `-o, --output` — output JSON file (default: `tomcat_processes.json`)
- `--jstack-dir` — directory used when `--save-jstack-files` is used (default: `jstacks`)
- `--no-jstack` — do not run `jstack` (skip thread dumps)
- `--save-jstack-files` — save per-PID jstack JSON files into `--jstack-dir` in addition to embedding

## Output format (summary)

The main JSON is an array of process objects. Each object contains the parsed `ps` columns and jstack information when available.

Example entry:

```json
{
  "UID": "user",
  "PID": "12345",
  "PPID": "1",
  "C": "0",
  "STIME": "12:34",
  "TTY": "pts/0",
  "TIME": "00:00:01",
  "CMD": "/path/to/java ... org.apache.catalina.startup.Bootstrap start",
  "jstack_saved": true,
  "jstack": {
    "raw": "<full jstack text>",
    "threads": [
      {"name":"main","header":"\"main\" #1 ...","state":"RUNNABLE","stack":["at ..."],"extras":[...]}
    ]
  }
}
```

If `jstack` failed for a PID, the entry will include:

```json
"jstack_saved": false,
"jstack_info": "<error string>"
```

When `--save-jstack-files` is used, a per-PID JSON file is written, e.g. `jstacks/jstack_12345.json`, and the entry's `jstack_info` will contain the saved path.

## Notes and caveats

- The jstack parser is best-effort. JVM `jstack` outputs vary across versions and vendors; this script extracts thread blocks, thread name, state, stack frames and other lines but does not guarantee exact field coverage for every JVM.
- Embedding full thread dumps increases the JSON size significantly. If you plan to collect many dumps, prefer `--save-jstack-files` or compress dumps.
- `jstack` may require root or appropriate permissions to attach to some processes; in that case the script will capture the error and continue.

## Next steps (optional enhancements)

- parse additional header fields in thread blocks (tid, nid, prio, daemon)
- extract locked monitors and synchronizers into structured fields
- compress saved per-PID files (gzip)
- add a `--regex` option to match processes using a custom regular expression

If you want any of these added, tell me which one to implement next.

---
Generated for the `memory-monitor` workspace. Keep this README with the script for quick reference.
