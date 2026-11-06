"use client";

import { createContext, useCallback, useContext, useSyncExternalStore, type ReactNode } from "react";

// The mechanic app speaks Hindi first (English on the Profile page switch). Short, plain words.
export type Lang = "hi" | "en";
const KEY = "im_m_lang";

const STRINGS = {
  appName: { hi: "IM मैकेनिक", en: "IM Mechanic" },
  today: { hi: "आज", en: "Today" },
  offers: { hi: "ऑफ़र", en: "Offers" },
  profile: { hi: "प्रोफ़ाइल", en: "Profile" },
  loading: { hi: "लोड हो रहा है…", en: "Loading…" },
  offline: { hi: "इंटरनेट नहीं है। सिग्नल मिलने पर फिर कोशिश करें।", en: "No internet. Try again when you have a signal." },
  error: { hi: "कुछ गड़बड़ हुई। फिर कोशिश करें।", en: "Something went wrong. Please try again." },
  retry: { hi: "फिर कोशिश करें", en: "Try again" },
  // sign in
  signInTitle: { hi: "साइन इन करें", en: "Sign in" },
  signInHint: { hi: "अपना मोबाइल नंबर डालें। हम SMS से कोड भेजेंगे।", en: "Enter your mobile number. We will send a code by SMS." },
  mobile: { hi: "मोबाइल नंबर", en: "Mobile number" },
  sendCode: { hi: "कोड भेजें", en: "Send code" },
  code: { hi: "6 अंकों का कोड", en: "6-digit code" },
  codeSent: { hi: "कोड भेजा गया:", en: "Code sent to" },
  codeHint: {
    hi: "कोड नहीं आया? अगर यह नंबर हमारे मैकेनिक का है तो कोड आ जाएगा। नहीं तो सपोर्ट को कॉल करें।",
    en: "No code? If this number belongs to one of our mechanics a code will arrive. Otherwise call support.",
  },
  signIn: { hi: "साइन इन", en: "Sign in" },
  badPhone: { hi: "10 अंकों का मोबाइल नंबर डालें", en: "Enter a 10-digit mobile number" },
  // duty
  onDuty: { hi: "ड्यूटी पर", en: "On duty" },
  offDuty: { hi: "ड्यूटी बंद", en: "Off duty" },
  goOnDuty: { hi: "ड्यूटी चालू करें", en: "Go on duty" },
  goOffDuty: { hi: "ड्यूटी बंद करें", en: "Go off duty" },
  dutyOnHint: { hi: "आपको नए काम के ऑफ़र मिलेंगे।", en: "You will get new job offers." },
  dutyOffHint: { hi: "अभी कोई नया ऑफ़र नहीं आएगा।", en: "No new offers will come now." },
  // today
  hello: { hi: "नमस्ते", en: "Hello" },
  openOffers: { hi: "नए ऑफ़र", en: "New offers" },
  seeOffers: { hi: "ऑफ़र देखें", en: "See offers" },
  myJobs: { hi: "आज के काम", en: "Today's jobs" },
  noJobs: { hi: "आज कोई काम नहीं।", en: "No jobs today." },
  // offers
  noOffers: { hi: "अभी कोई ऑफ़र नहीं। यह पेज खुद अपडेट होता है।", en: "No offers right now. This page updates itself." },
  accept: { hi: "काम लें", en: "Accept" },
  reject: { hi: "मना करें", en: "Reject" },
  secondsLeft: { hi: "सेकंड बचे", en: "seconds left" },
  expired: { hi: "समय खत्म", en: "Expired" },
  approxArea: { hi: "लगभग जगह", en: "Approx. area" },
  approxKm: { hi: "लगभग {n} किमी (सीधी दूरी)", en: "about {n} km (straight line)" },
  car: { hi: "गाड़ी", en: "Car" },
  problem: { hi: "समस्या", en: "Problem" },
  jobType: { hi: "काम का प्रकार", en: "Job type" },
  urgent: { hi: "जल्दी", en: "Urgent" },
  safety: { hi: "सुरक्षा: पहले ग्राहक को रुकने को कहें", en: "Safety: tell the customer to stop driving" },
  addressAfterAccept: { hi: "पूरा पता काम लेने के बाद दिखेगा।", en: "The full address shows after you accept." },
  offerGone: { hi: "यह ऑफ़र अब खुला नहीं है।", en: "This offer is no longer open." },
  // job
  job: { hi: "काम", en: "Job" },
  address: { hi: "पता", en: "Address" },
  openMap: { hi: "मैप में खोलें", en: "Open in Maps" },
  customer: { hi: "ग्राहक", en: "Customer" },
  callCustomer: { hi: "ग्राहक को कॉल करें", en: "Call customer" },
  calling: { hi: "आपके फ़ोन पर कॉल आ रही है। उठाएँ, फिर ग्राहक से जुड़ जाएँगे।", en: "We are calling your phone now. Pick up to be connected." },
  notes: { hi: "ग्राहक का नोट", en: "Customer's note" },
  status: { hi: "स्थिति", en: "Status" },
  eta: { hi: "पहुँचने का समय", en: "Arrival time" },
  etaQuestion: { hi: "कितने मिनट में पहुँचेंगे?", en: "In how many minutes will you arrive?" },
  minutes: { hi: "मिनट", en: "min" },
  etaSaved: { hi: "ग्राहक को बता दिया: लगभग {n} मिनट", en: "Customer told: about {n} minutes" },
  startTravel: { hi: "निकल रहा हूँ", en: "On my way" },
  arrived: { hi: "पहुँच गया", en: "I have arrived" },
  startWork: { hi: "काम शुरू", en: "Start work" },
  finish: { hi: "काम पूरा करें", en: "Finish job" },
  done: { hi: "काम पूरा हुआ। धन्यवाद!", en: "Job done. Thank you!" },
  // fault picker
  whatFault: { hi: "असल में क्या खराबी थी?", en: "What was the actual fault?" },
  searchFault: { hi: "खराबी खोजें (हिंदी या English)", en: "Search the fault (Hindi or English)" },
  aiGuess: { hi: "AI का अंदाज़ा", en: "AI's guess" },
  other: { hi: "दूसरी / पक्का नहीं", en: "Other / not sure" },
  otherNote: { hi: "क्या मिला? छोटा नोट लिखें", en: "What did you find? A short note" },
  workNotes: { hi: "आपने क्या किया (वैकल्पिक)", en: "What you did (optional)" },
  pickFault: { hi: "खराबी चुनें, या 'दूसरी' के साथ नोट लिखें।", en: "Pick the fault, or 'Other' with a note." },
  confirmFinish: { hi: "पूरा करें और भेजें", en: "Finish and send" },
  // profile
  language: { hi: "भाषा", en: "Language" },
  alerts: { hi: "इस फ़ोन पर ऑफ़र की सूचना", en: "Offer alerts on this phone" },
  alertsOn: { hi: "सूचना चालू", en: "Alerts on" },
  turnOnAlerts: { hi: "सूचना चालू करें", en: "Turn on alerts" },
  alertsBlocked: { hi: "सूचना ब्लॉक है। ब्राउज़र की सेटिंग में अनुमति दें।", en: "Alerts are blocked. Allow them in the browser's settings." },
  install: { hi: "होम स्क्रीन पर जोड़ें: ब्राउज़र मेन्यू में 'Add to Home screen'।", en: "Add to your home screen: browser menu > 'Add to Home screen'." },
  signOut: { hi: "साइन आउट", en: "Sign out" },
  statusNames: {
    hi: { accepted: "काम लिया", en_route: "रास्ते में", arrived: "पहुँच गए", in_progress: "काम चल रहा है", completed: "पूरा" },
    en: { accepted: "Accepted", en_route: "On the way", arrived: "Arrived", in_progress: "Working", completed: "Done" },
  },
} as const;

type Key = Exclude<keyof typeof STRINGS, "statusNames">;

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "hi", setLang: () => undefined });

// The choice is kept in localStorage; the server (and the first paint) uses Hindi.
const listeners = new Set<() => void>();
let fallback: Lang = "hi"; // when localStorage is not available (private mode)

function readLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "en" || saved === "hi" ? saved : fallback;
  } catch {
    return fallback;
  }
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function LangProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, readLang, () => "hi" as Lang);
  const setLang = useCallback((l: Lang) => {
    fallback = l;
    try {
      localStorage.setItem(KEY, l);
    } catch {
      // not remembered after a reload
    }
    listeners.forEach((cb) => cb());
  }, []);
  return (
    <Ctx.Provider value={{ lang, setLang }}>
      <div lang={lang === "hi" ? "hi" : "en"} className="contents">
        {children}
      </div>
    </Ctx.Provider>
  );
}

export function useLang() {
  return useContext(Ctx);
}

export function useT() {
  const { lang } = useContext(Ctx);
  return useCallback(
    (key: Key, vars?: Record<string, string | number>) => {
      let text: string = STRINGS[key][lang];
      for (const [k, v] of Object.entries(vars ?? {})) text = text.replace(`{${k}}`, String(v));
      return text;
    },
    [lang],
  );
}

export function useStatusName() {
  const { lang } = useContext(Ctx);
  return (status: string) => (STRINGS.statusNames[lang] as Record<string, string>)[status] ?? status;
}
