// The language the customer last used on the site (Phase 5.5). Sent with a service request, so the notifications
// about it (Phase 5.2: SMS, WhatsApp, push) come in the same language. Kept in localStorage: nothing personal.
import { isLocale, type Locale } from "./config";

export const LANGUAGE_KEY = "im.lang";

export function rememberLanguage(locale: Locale) {
  try {
    localStorage.setItem(LANGUAGE_KEY, locale);
  } catch {
    // private mode: notifications fall back to the language detected from the customer's own words
  }
}

/** The remembered language, or null when the customer never opened the English or Hindi pages here. */
export function rememberedLanguage(): Locale | null {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    return isLocale(saved) ? saved : null;
  } catch {
    return null;
  }
}
