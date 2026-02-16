"""
Filter intended config for digital twin deployment.

Removes config blocks (and their children) that are not suitable for lab environments,
e.g. RADIUS, TACACS, management interfaces, IP addresses that won't work in a lab.
"""


def _get_indent(line):
    """Return the number of leading spaces on the line."""
    stripped = line.lstrip(" \t")
    return len(line) - len(stripped) if stripped else 0


def filter_config_remove_blocks(config_content: str, patterns: list) -> str:
    """
    Remove config blocks matching any of the given patterns.

    When a line matches a pattern (pattern in line), that line and all more-indented
    lines below it are removed until a line at the same or lower indent is reached.
    Handles Cisco-style and similar configs where child config is indented.

    Args:
        config_content: Raw config string (e.g. from Golden Config intended).
        patterns: List of strings to match. If a line contains a pattern, the block
            is removed. E.g. ["GigabitEthernet0/0", "radius-server"] removes interface
            GigabitEthernet0/0 (and its children) and radius-server blocks.

    Returns:
        Filtered config string.
    """
    if not config_content or not patterns:
        return config_content

    lines = config_content.split("\n")
    to_remove = set()

    for i, line in enumerate(lines):
        if i in to_remove:
            continue
        for pattern in patterns:
            if pattern and pattern in line:
                start_indent = _get_indent(line)
                to_remove.add(i)
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_indent = _get_indent(next_line)
                    # Stop at a non-empty line at same or lower indent
                    if next_line.strip() and next_indent <= start_indent:
                        break
                    to_remove.add(j)
                    j += 1
                break  # Found a match for this line, move to next line

    result_lines = [line for idx, line in enumerate(lines) if idx not in to_remove]
    return "\n".join(result_lines)
