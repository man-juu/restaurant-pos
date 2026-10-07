import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '../locales/en/common.json'
import id from '../locales/id/common.json'

export const resources = { en: { common: en }, id: { common: id } } as const
export const LANGUAGES = ['id', 'en'] as const
const STORAGE_KEY = 'pos.language'

function storedLanguage(): string {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'en' || value === 'id' ? value : 'id'
  } catch {
    return 'id' // private mode or blocked storage: Indonesian default
  }
}

export function setLanguage(language: (typeof LANGUAGES)[number]): void {
  void i18n.changeLanguage(language)
  try {
    localStorage.setItem(STORAGE_KEY, language)
  } catch {
    // preference only; ignore storage failures
  }
}

void i18n.use(initReactI18next).init({
  resources,
  lng: storedLanguage(),
  fallbackLng: 'en',
  defaultNS: 'common',
  interpolation: { escapeValue: false }, // React already escapes output
})

// Keep <html lang> in sync (screen readers, spell check, hyphenation), including at start-up.
const syncLang = (language: string) => {
  if (typeof document !== 'undefined') document.documentElement.lang = language
}
i18n.on('languageChanged', syncLang)
syncLang(i18n.language)

export default i18n
