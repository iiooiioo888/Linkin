/**
 * i18n 初始化（zh-TW / en）。預設繁中。
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import zhTW from './locales/zh-TW.json';

void i18n.use(initReactI18next).init({
  resources: {
    'zh-TW': { translation: zhTW },
    en: { translation: en },
  },
  lng: localStorage.getItem('evoloop.locale') || 'zh-TW',
  fallbackLng: 'zh-TW',
  interpolation: { escapeValue: false },
});

export function setLocale(lng: 'zh-TW' | 'en') {
  localStorage.setItem('evoloop.locale', lng);
  void i18n.changeLanguage(lng);
}

export default i18n;
