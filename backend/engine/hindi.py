"""Hindi in Devanagari to the romanised Hinglish the knowledge is written in (customers write "brake fail ho
gaye", the data has no Devanagari). Rule-based and offline.

Car words in Hindi are mostly English loanwords, so a glossary maps them back to English ("ब्रेक" -> "brake");
plain transliteration would give "brek". The glossary was built from the most frequent English words in the
dataset's customer phrases (plus a few common part names); it needs review by a Hindi speaker.
"""

from __future__ import annotations

import re

DEVANAGARI_WORD = re.compile(r"[ऀ-ॿ]+")
VIRAMA, NUKTA, ANUSVARA, CHANDRABINDU, VISARGA = "्", "़", "ं", "ँ", "ः"

VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ॲ": "e",
}  # fmt: skip
MATRAS = {
    "ा": "aa", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}  # fmt: skip
CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}  # fmt: skip
NUKTA_CONSONANTS = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f"}

# English loanwords (from the dataset's most frequent English words) and Hindi words whose usual Hinglish
# spelling differs from the plain transliteration. Keys are written without nukta.
GLOSSARY = {
    # car and fault words
    "लाइट": "light", "स्टार्ट": "start", "कार": "car", "इंजन": "engine", "इंजिन": "engine", "ब्रेक": "brake",
    "बैटरी": "battery", "बेटरी": "battery", "स्मेल": "smell", "गियर": "gear", "बेल्ट": "belt",
    "वार्निंग": "warning", "प्रॉब्लम": "problem", "सीएनजी": "cng", "एसी": "ac", "डोर": "door", "मिरर": "mirror",
    "चेक": "check", "स्टीयरिंग": "steering", "स्टेयरिंग": "steering", "पेट्रोल": "petrol", "ऑयल": "oil",
    "आयल": "oil", "सेंसर": "sensor", "लॉक": "lock", "सेल्फ": "self", "पाइप": "pipe", "एयरबैग": "airbag",
    "डीजल": "diesel", "बोनट": "bonnet", "पंप": "pump", "फ्यूज": "fuse", "पावर": "power",
    "डैशबोर्ड": "dashboard", "वायर": "wire", "लीक": "leak", "स्पीड": "speed", "वॉटर": "water", "फ्यूल": "fuel",
    "साइड": "side", "प्लेट": "plate", "टायर": "tyre", "नॉइज": "noise", "व्हील": "wheel", "बटन": "button",
    "स्टक": "stuck", "ऑफ": "off", "डेड": "dead", "पेडल": "pedal", "स्विच": "switch", "क्लच": "clutch",
    "आइडल": "idle", "साइलेंसर": "silencer", "हाईवे": "highway", "ग्लास": "glass", "पिकअप": "pickup",
    "लूज": "loose", "एरर": "error", "विंडो": "window", "हॉर्न": "horn", "स्क्रीन": "screen", "एबीएस": "abs",
    "मैकेनिक": "mechanic", "बंपर": "bumper", "पार्किंग": "parking", "एक्सीडेंट": "accident", "फ्रंट": "front",
    "साउंड": "sound", "रिमोट": "remote", "कोड": "code", "ब्लिंक": "blink", "रिले": "relay", "फॉल्ट": "fault",
    "डाउन": "down", "स्लो": "slow", "प्लग": "plug", "सीट": "seat", "चार्जिंग": "charging", "कवर": "cover",
    "सर्विस": "service", "कैमरा": "camera", "चेंज": "change", "कूलेंट": "coolant", "स्मोक": "smoke",
    "स्टार्टर": "starter", "रेस": "race", "रोड": "road", "फिल्टर": "filter", "रिवर्स": "reverse", "गैस": "gas",
    "ट्रैफिक": "traffic", "एग्जॉस्ट": "exhaust", "सिग्नल": "signal", "क्रैक": "crack", "फुल": "full",
    "वाइपर": "wiper", "ऑटोमैटिक": "automatic", "फ्लड": "flood", "सिस्टम": "system", "म्यूजिक": "music",
    "बूट": "boot", "प्लास्टिक": "plastic", "पैड": "pad", "पंक्चर": "puncture", "टेम्परेचर": "temperature",
    "रेडिएटर": "radiator", "ब्लोअर": "blower", "मोटर": "motor", "कूलिंग": "cooling", "फैन": "fan",
    "हीटर": "heater", "अल्टरनेटर": "alternator", "डायनमो": "dynamo", "ट्यूब": "tube", "एयर": "air",
    "प्रेशर": "pressure", "वाल्व": "valve", "स्पार्क": "spark", "फेल": "fail", "हैंड": "hand", "मीटर": "meter",
    "स्लिप": "slip", "स्पंजी": "spongy", "हैंडब्रेक": "handbrake", "डिस्क": "disc", "रिम": "rim",
    "ओवरहीट": "overheat", "स्टेपनी": "stepney", "जैक": "jack", "चाबी": "chabi", "पेट्रोल पंप": "petrol pump",
    # Hindi words: the Hinglish spelling the data uses
    "नहीं": "nahi", "नही": "nahi", "है": "hai", "हैं": "hain", "में": "mein", "रहा": "raha", "रही": "rahi",
    "रहे": "rahe", "गया": "gaya", "गई": "gayi", "गयी": "gayi", "गए": "gaye", "आवाज": "awaaz", "पानी": "paani",
    "धुआं": "dhuan", "धुआँ": "dhuan", "गरम": "garam", "गर्म": "garam", "ठंडा": "thanda", "ठंडी": "thandi",
    "हवा": "hawa", "बंद": "band", "खराब": "kharab", "कम": "kam", "ज्यादा": "zyada", "बहुत": "bahut",
    "अटक": "atak", "टूट": "toot", "झटके": "jhatke", "झटका": "jhatka", "आग": "aag", "गाड़ी": "gaadi",
    "गाडी": "gaadi", "चलते": "chalte", "समय": "samay", "बार": "baar", "बदबू": "badbu", "भारी": "bhaari",
    "नीचे": "neeche", "ऊपर": "upar", "अंदर": "andar", "बाहर": "bahar", "पीछे": "peeche", "आगे": "aage",
    "रिसाव": "leak", "उभार": "bulge", "फट": "phat", "फूल": "phool", "चीं": "chee",
}  # fmt: skip


def _plain(word: str) -> str:
    """Letter-by-letter transliteration with the inherent 'a', dropped at the end of a word."""
    out: list[str] = []
    chars = list(word)
    i = 0
    while i < len(chars):
        c = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if c in CONSONANTS:
            base = CONSONANTS[c]
            if nxt == NUKTA:
                base = NUKTA_CONSONANTS.get(c, base)
                i += 1
                nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == VIRAMA:
                out.append(base)
                i += 2
                continue
            if nxt in MATRAS:
                out.append(base + MATRAS[nxt])
                i += 2
                continue
            last = i + 1 >= len(chars) or chars[i + 1] in (ANUSVARA, CHANDRABINDU, VISARGA) and i + 2 >= len(chars)
            out.append(base if last else base + "a")
        elif c in VOWELS:
            out.append(VOWELS[c])
        elif c in (ANUSVARA, CHANDRABINDU):
            out.append("n")
        elif c == VISARGA:
            out.append("h")
        elif c.isascii():
            out.append(c)
        i += 1
    return "".join(out)


def transliterate(text: str) -> str:
    """Devanagari words to Hinglish (glossary first, then letter rules); other text unchanged."""

    def word(m: re.Match) -> str:
        w = m.group(0).replace(NUKTA, "") if m.group(0).replace(NUKTA, "") in GLOSSARY else m.group(0)
        known = GLOSSARY.get(w) or GLOSSARY.get(w.replace(NUKTA, ""))
        if known:
            return known
        plain = _plain(m.group(0))
        return plain[:-1] if len(plain) > 4 and plain.endswith("aa") else plain  # "puraa" -> "pura"

    return DEVANAGARI_WORD.sub(word, text)


# Hindi grammar words: they say nothing about the fault, and in Hinglish they match every kind of message
# ("gaya", "nahi", "raha"). Left out of the Hinglish form used for matching.
FUNCTION_WORDS = frozenset(
    "है हैं हो था थी थे रहा रही रहे गया गई गयी गए नहीं नही पर से की का के को में मे भी और तो ही ने कि "
    "पूरा पूरी बहुत दे देता देती आता आती आते जाता जाती जाते लगता लगती लगते कर करता करती करते करने होता होती "
    "होते हुआ हुई मेरी मेरा मेरे वाला वाली अब कुछ एक बार".split()
)


def content_words(text: str) -> str:
    """The Hinglish form of the text's content words (Hindi grammar words dropped)."""
    words = [w for w in DEVANAGARI_WORD.findall(text) if w.replace(NUKTA, "") not in FUNCTION_WORDS]
    latin = DEVANAGARI_WORD.sub(" ", text)
    return " ".join(part for part in (transliterate(" ".join(words)), latin.strip()) if part)


def has_devanagari(text: str) -> bool:
    return bool(DEVANAGARI_WORD.search(text))


def expand(text: str) -> str:
    """The text plus the Hinglish form of its content words when it has Devanagari (both are matched)."""
    return f"{text} {content_words(text)}" if has_devanagari(text) else text
