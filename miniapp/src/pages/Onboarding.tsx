// A newcomer's first minutes: a name, a race and a class, and the hero is born (the same rules as the bot's /start).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Emblem, Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { iconFor, ui } from "../lib/icons";

interface Option { id: string; name: string; emoji: string; about: string }

export default function Onboarding({ onDone, toast }: { onDone: () => void; toast: (text: string, error?: boolean) => void }) {
  const options = useQuery({ queryKey: ["onboarding"], queryFn: () => call<{ races: Option[]; classes: Option[] }>("onboarding") });
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [race, setRace] = useState("");
  const [cls, setCls] = useState("");

  const create = async () => {
    try {
      await call("register", { name: name.trim(), race, class: cls });
      toast("قهرمان شما به دنیا آمد!");
      onDone();
    } catch (error) {
      toast(error instanceof Error ? error.message : "نشد", true);
      if (step === 2) setStep(0);
    }
  };

  const list = step === 1 ? options.data?.races : options.data?.classes;
  const picked = step === 1 ? race : cls;
  return (
    <div className="page" style={{ paddingBottom: 30 }}>
      <div style={{ textAlign: "center", margin: "18px 0 16px" }}>
        <div style={{ display: "grid", placeItems: "center" }}><Emblem icon={ui("ui.emblem")} size={96} rarity={5} round /></div>
        <h1 className="title gold-text" style={{ fontSize: 30, marginTop: 10 }}>
          {step === 0 ? "قهرمان خود را بسازید" : step === 1 ? "نژاد خود را برگزینید" : "راه نبردتان را برگزینید"}
        </h1>
        <p className="muted small">گام {["۱", "۲", "۳"][step]} از ۳</p>
      </div>

      {step === 0 && (
        <div className="card gilded stack">
          <p>نام قهرمانتان را بنویسید (۲ تا ۱۶ حرف).</p>
          <input className="field" autoFocus maxLength={16} value={name} onChange={(event) => setName(event.target.value)} placeholder="مثلاً آرش" />
          <Button kind="gold" disabled={name.trim().length < 2} onClick={() => setStep(1)}>ادامه</Button>
        </div>
      )}

      {step > 0 && (!list ? <Skeleton height={76} /> : (
        <div className="stack">
          {list.map((option) => (
            <button key={option.id} className={`choice ${picked === option.id ? "on" : ""}`} onClick={() => (step === 1 ? setRace(option.id) : setCls(option.id))}>
              <Emblem icon={iconFor(step === 1 ? "race" : "class", option.id, option.emoji)} size={58} rarity={picked === option.id ? 5 : 4} />
              <div className="grow">
                <div className="title" style={{ fontSize: 18 }}>{option.name}</div>
                <div className="small muted">{option.about.replace(/\p{Extended_Pictographic}️?/gu, "")}</div>
              </div>
              {picked === option.id && <Icon name={ui("ui.check")} size={24} />}
            </button>
          ))}
          <div className="row" style={{ marginTop: 6 }}>
            <Button onClick={() => setStep(step - 1)}>بازگشت</Button>
            {step === 1
              ? <Button kind="gold" disabled={!race} onClick={() => setStep(2)}>ادامه</Button>
              : <Button kind="gold" disabled={!cls} onClick={create}>آغاز ماجرا</Button>}
          </div>
        </div>
      ))}
    </div>
  );
}
