import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '../locales/en/common.json'
import id from '../locales/id/common.json'

export const resources = { en: { common: en }, id: { common: id } } as const

void i18n.use(initReactI18next).init({
  resources,
  lng: 'id',
  fallbackLng: 'en',
  defaultNS: 'common',
  interpolation: { escapeValue: false }, // React already escapes output
})

export default i18n
