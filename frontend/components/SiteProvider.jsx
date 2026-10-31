'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../lib/api';

const defaults = { site_name: 'aikadr', logo_url: '/brand/aikadr-square.png', theme: 'midnight', accent_color: '#D8B66B',
  hero_kicker: 'НОВЫЙ ВЗГЛЯД НА КИНО', hero_title: 'Истории за гранью привычного',
  hero_subtitle: 'Авторские ИИ-сериалы. Неожиданные миры. Ваше следующее открытие.', hero_background_url: '' };
const SiteContext = createContext({ site: defaults, refresh: () => {} });
export const useSite = () => useContext(SiteContext);
export default function SiteProvider({ children }) {
  const [site, setSite] = useState(defaults);
  const refresh = () => api('/site').then(setSite);
  useEffect(() => { refresh().catch(() => {}); }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = site.theme;
    document.documentElement.style.setProperty('--accent', site.accent_color);
    document.documentElement.style.setProperty('--studio-green', site.accent_color);
    document.title = `${site.site_name} — истории нового времени`;
  }, [site]);
  return <SiteContext.Provider value={{ site, refresh }}>{children}</SiteContext.Provider>;
}
