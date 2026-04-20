"""
Filter intended config for digital twin deployment.

Removes config blocks (and their children) that are not suitable for lab environments,
e.g. RADIUS, TACACS, management interfaces, IP addresses that won't work in a lab.

Also supports:
- REPLACE_CONFIG_PATTERNS: replace strings (e.g. group radius -> local for enterprises)
- PLATFORM_ADD_CONFIG_LINES: add platform-specific config lines (e.g. fallback auth)
- PLATFORM_REMOVE_CONFIG_LINES: platform-specific remove patterns (in addition to REMOVE_CONFIG_LINES)
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


def filter_config_replace(config_content: str, patterns: list) -> str:
    """
    Replace strings in config (e.g. for enterprises: switch radius/tacacs to local).

    Args:
        config_content: Raw config string.
        patterns: List of (old_string, new_string) tuples. E.g. [("group radius", "local")].

    Returns:
        Config string with replacements applied.
    """
    if not config_content or not patterns:
        return config_content

    result = config_content
    for old_str, new_str in patterns:
        if old_str and new_str is not None:
            result = result.replace(old_str, new_str)
    return result


def filter_config_append_add_lines(config_content: str, platform_key: str, username: str, password: str, platform_add_config_lines: dict) -> str:
    """
    Append platform-specific config lines when configured (e.g. fallback auth).

    Args:
        config_content: Raw config string (after remove and replace).
        platform_key: Platform key (e.g. "arista_eos") from device.platform.name.
        username: Username for {username} placeholder.
        password: Password for {password} placeholder.
        platform_add_config_lines: Dict mapping platform_key -> list of config lines.

    Returns:
        Config string with add lines appended if platform is in the map.
    """
    if not platform_add_config_lines or not isinstance(platform_add_config_lines, dict):
        return config_content

    lines = platform_add_config_lines.get(platform_key)
    if not lines:
        return config_content

    # Resolve placeholders
    resolved = []
    for line in lines:
        if isinstance(line, str):
            line = line.replace("{username}", username).replace("{password}", password)
            resolved.append(line)
    if not resolved:
        return config_content

    content = config_content.rstrip()
    block = "\n".join(resolved)

    # Insert before "end" if present (Arista, Cisco) so auth is part of config
    if content:
        lines_list = content.split("\n")
        insert_idx = None
        for i in range(len(lines_list) - 1, -1, -1):
            if lines_list[i].strip() == "end":
                insert_idx = i
                break
        if insert_idx is not None:
            before = "\n".join(lines_list[:insert_idx]).rstrip()
            after = "\n".join(lines_list[insert_idx:])
            return f"{before}\n!\n{block}\n!\n{after}" if before else f"{block}\n!\n{after}"
    return f"{content}\n!\n{block}\n" if content else block


def build_minimal_config_from_add_lines(platform_key: str, username: str, password: str, platform_add_config_lines: dict) -> str:
    """
    Build a minimal config containing only the PLATFORM_ADD_CONFIG_LINES for that platform.

    Used when no intended config exists and platform is in PLATFORM_ADD_CONFIG_LINES.
    """
    if not platform_add_config_lines or not isinstance(platform_add_config_lines, dict):
        return ""
    lines = platform_add_config_lines.get(platform_key)
    if not lines:
        return ""
    resolved = []
    for line in lines:
        if isinstance(line, str):
            line = line.replace("{username}", username).replace("{password}", password)
            resolved.append(line)
    if not resolved:
        return ""
    return "!\n" + "\n".join(resolved) + "\n"
