const FA = "۰۱۲۳۴۵۶۷۸۹";

/** A number in Persian digits with thousands separators. */
export function fa(value: number | string): string {
  const text = typeof value === "number" ? Math.round(value).toLocaleString("en-US") : value;
  return text.replace(/\d/g, (d) => FA[Number(d)]).replace(/,/g, "٬");
}

export function duration(seconds: number): string {
  if (seconds <= 0) return "آماده";
  if (seconds < 60) return `${fa(seconds)} ثانیه`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${fa(minutes)} دقیقه`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${fa(hours)} ساعت و ${fa(rest)} دقیقه` : `${fa(hours)} ساعت`;
}

export const ROLE_NAMES: Record<string, string> = { leader: "مالک", deputy: "قائم‌مقام", elder: "ریش‌سفید", member: "عضو" };
