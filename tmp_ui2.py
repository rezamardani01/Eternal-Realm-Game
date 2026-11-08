def sub(p, o, n, count=1):
    s = open(p, encoding="utf-8").read()
    assert o in s, (p, o[:70])
    open(p, "w", encoding="utf-8").write(s.replace(o, n, count))

sub("eternal_realm/bot/pet_panel.py", "هنوز حیوان خانگیی ندارید.", "هنوز حیوان خانگی ندارید.")
C = "eternal_realm/bot/clan_panel.py"
NL = chr(92) + "n"
sub(C, '''    text = (
        f"{ROLES[m['role']][0]} {bold(m['name']) if not c.is_group else '[' + m['name'] + '](uid:' + str(m['platform_user_id']) + ')'}\n\n"
        f"🎖️ مقام: {ROLES[m['role']][1]}\n\n"
        f"⭐ سطح: {fa(m['level'])}\n\n"
        f"🪙 کمک به خزانه: {fa(m['donated'])} سکه"
    )''', '''    text = (
        f"{ROLES[m['role']][0]} {bold(m['name']) if not c.is_group else '[' + m['name'] + '](uid:' + str(m['platform_user_id']) + ')'}\n\n"
        f"🎖️ مقام: {ROLES[m['role']][1]}\n"
        f"⭐ سطح: {fa(m['level'])}\n"
        f"🪙 کمک به خزانه: {fa(m['donated'])} سکه"
    )''')
sub(C, '''        f"💰 {bold('خزانه‌ی خاندان')}\n\n"
        f"🪙 موجودی خزانه: {fa(mine.treasury)} سکه\n\n"
        f"⭐ سطح خاندان: {fa(mine.level)}\n\n"
        f"🎯 برای سطح بعد: {fa(max(0, need - mine.donated))} سکه‌ی دیگر\n\n"
        f"👛 کیف شما: {fa(c.player.gold)} سکه\n\n"''', '''        f"💰 {bold('خزانه‌ی خاندان')}\n\n"
        f"🪙 موجودی خزانه: {fa(mine.treasury)} سکه\n"
        f"⭐ سطح خاندان: {fa(mine.level)}\n"
        f"🎯 برای سطح بعد: {fa(max(0, need - mine.donated))} سکه‌ی دیگر\n\n"
        f"👛 کیف شما: {fa(c.player.gold)} سکه\n\n"''')
sub(C, '''        f"{bold('جنگ خاندان‌ها')}''', '''        f"{bold('جنگ خاندان‌ها')}''') if False else None
