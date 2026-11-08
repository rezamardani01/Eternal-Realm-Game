def sub(p, o, n):
    s = open(p, encoding="utf-8").read()
    assert o in s, (p, o[:60])
    open(p, "w", encoding="utf-8").write(s.replace(o, n, 1))

T = "eternal_realm/shared/text.py"
sub(T, '''    """Bale Markdown bold. Put a space before it and after it (as the Bale docs require)."""
    return f"**{value}**"''', '''    """Bale Markdown bold: a single star on each side (Bale has no double-star bold)."""
    return f"*{value}*"''')
sub(T, '''    if "**" in line or "](uid:" in line or not line.strip():''', '''    if "*" in line or "](uid:" in line or not line.strip():''')
sub(T, '''        return f"{match.group(1)} **{match.group(2).strip()}**"
    return f"**{line.strip()}**"''', '''        return f"{match.group(1)} *{match.group(2).strip()}*"
    return f"*{line.strip()}*"''')
sub(T, '''    if "**" in text:
        return text''', '''    if "*" in text:
        return text''')
sub("eternal_realm/bot/views.py", "bold (with a space around the ``**`` markers, as Bale requires)", "bold (single ``*`` markers, the only bold Bale understands)")
U = "tests/test_ui_rules.py"
sub(U, '''== "⚡ **انرژی شما کافی نیست**"''', '''== "⚡ *انرژی شما کافی نیست*"''')
sub(U, '''== "**سلام**\nخط دوم"''', '''== "*سلام*\nخط دوم"''')
sub(U, '''headline("🎉 **از قبل بولد**\nمتن") == "🎉 **از قبل بولد**\nمتن"''', '''headline("🎉 *از قبل بولد*\nمتن") == "🎉 *از قبل بولد*\nمتن"''')
sub("tests/test_panel.py", '''assert "**" in views.welcome()''', '''assert "*" in views.welcome() and "**" not in views.welcome()''')
