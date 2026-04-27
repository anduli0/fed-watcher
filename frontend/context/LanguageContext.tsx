"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { Lang, t } from "@/lib/i18n";

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  T: typeof t.en;
}

const LanguageContext = createContext<LangCtx>({
  lang: "en",
  setLang: () => {},
  T: t.en,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    const saved = localStorage.getItem("fw_lang") as Lang | null;
    if (saved === "en" || saved === "ko") setLangState(saved);
  }, []);

  function setLang(l: Lang) {
    setLangState(l);
    localStorage.setItem("fw_lang", l);
  }

  return (
    <LanguageContext.Provider value={{ lang, setLang, T: t[lang] as typeof t.en }}>
      {children}
    </LanguageContext.Provider>
  );
}

export const useLang = () => useContext(LanguageContext);
