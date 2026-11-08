p = "eternal_realm/bot/transfer_panel.py"
s = open(p, encoding="utf-8").read()
a = s.index("    lines = [\n        f\"🎁 {bold('هدیه رسید!')}\"")
b = s.index("    return Screen(\"\n\".join(lines), [])", a)
NL = chr(92) + "n"
new = (
    "    lines = [\n"
    "        f\"🎁 {bold('هدیه رسید!')}\",\n"
    "        \"\",\n"
    "        f\"از: {_who(c, c.player)}\",\n"
    "        f\"به: {_who(c, other)}\",\n"
    "        f\"هدیه: {receipt.what}\",\n"
    "    ]\n"
    "    if receipt.left is not None:\n"
    "        lines += [\"\", f\"🏦 امروز می‌توانید {fa(receipt.left)} {receipt.unit}‌ی دیگر ببخشید.\"]\n"
    "    if c.message is not None:\n"
    "        dm = (\n"
    f"            f\"🎁 {{bold('هدیه‌ای برای شما رسید!')}}{NL}{NL}\"\n"
    f"            f\"از: {{c.player.name}}{NL}\"\n"
    f"            f\"هدیه: {{receipt.what}}{NL}{NL}\"\n"
    "            \"از کیف و کوله‌پشتی‌تان ببینیدش.\"\n"
    "        )\n"
    "        with contextlib.suppress(BaleAPIError):\n"
    "            await c.message.bot.send_message(other.platform_user_id, dm)\n"
)
open(p, "w", encoding="utf-8").write(s[:a] + new + s[b:])
