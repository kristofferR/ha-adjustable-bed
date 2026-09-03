from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def build_static_tool(
    root: Path,
    *,
    outputs: dict[str, dict[str, str]],
    modes: dict[str, str] | None = None,
    diagnostics: dict[str, str] | None = None,
    version_mode: str = "normal",
    extra_source: str = "",
) -> Path:
    """Build a tiny static fixture so sandbox tests need no host runtime."""

    tool_root = Path(tempfile.mkdtemp(prefix="tool-runtime-", dir=root))
    source = tool_root / "fixture-tool.c"
    binary = tool_root / "fixture-tool"
    route_blocks: list[str] = []
    for route, members in outputs.items():
        writes = "\n".join(
            f"write_member(output, {json.dumps(path)}, {json.dumps(content)});"
            for path, content in members.items()
        )
        route_blocks.append(f"if (strcmp(route, {json.dumps(route)}) == 0) {{ {writes} }}")
    mode_blocks = "\n".join(
        f"if (strcmp(route, {json.dumps(route)}) == 0) mode = {json.dumps(mode)};"
        for route, mode in (modes or {}).items()
    )
    diagnostic_blocks = "\n".join(
        f'if (strcmp(route, {json.dumps(route)}) == 0) fprintf(stderr, "%s\\n", {json.dumps(value)});'
        for route, value in (diagnostics or {}).items()
    )
    source.write_text(
        f"""
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

static void mkdirs(char *path) {{
    for (char *p = path + 1; *p; p++) {{
        if (*p == '/') {{ *p = 0; mkdir(path, 0700); *p = '/'; }}
    }}
}}
static void write_member(const char *root, const char *relative, const char *payload) {{
    char path[8192];
    snprintf(path, sizeof(path), "%s/%s", root, relative);
    mkdirs(path);
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) exit(91);
    size_t length = strlen(payload);
    if (write(fd, payload, length) != (ssize_t)length) exit(92);
    close(fd);
}}
int main(int argc, char **argv) {{
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {{
        if (strcmp({json.dumps(version_mode)}, "non-utf8") == 0) {{ unsigned char x=255; write(1,&x,1); return 0; }}
        if (strcmp({json.dumps(version_mode)}, "empty") == 0) return 0;
        puts("fixture-tool 1.2.3"); return 0;
    }}
    if (argc < 4) return 90;
    const char *route = argv[argc-3], *input = argv[argc-2], *output = argv[argc-1];
    const char *mode = "";
    {mode_blocks}
    {diagnostic_blocks}
    if (strcmp(mode, "crash") == 0) return 17;
    if (strcmp(mode, "noisy") == 0) {{ char b[4096]; memset(b,'x',sizeof(b)); write(1,b,sizeof(b)); }}
    if (strcmp(mode, "timeout") == 0) sleep(2);
    if (strcmp(mode, "mutate-input") == 0) {{ chmod(input,0600); int fd=open(input,O_WRONLY|O_TRUNC); write(fd,"mutated",7); close(fd); }}
    if (strcmp(mode, "symlink") == 0) {{ char p[8192]; snprintf(p,sizeof(p),"%s/unsafe",output); symlink("/etc/passwd",p); return 0; }}
    if (strcmp(mode, "partial") == 0) return 0;
    {extra_source}
    {" ".join(route_blocks)}
    return 0;
}}
""",
        encoding="utf-8",
    )
    subprocess.run(
        ["gcc", "-static", "-O2", "-s", str(source), "-o", str(binary)],
        check=True,
        capture_output=True,
    )
    source.unlink()
    return binary
