import { en } from './en';
import { es, type TranslationSchema } from './es';
import type { Locale } from '../types/mocap';

export const translations: Record<Locale, TranslationSchema> = {
  es,
  en,
};

