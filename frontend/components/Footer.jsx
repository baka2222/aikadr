'use client';
import Brand from './Brand';
import { useSite } from './SiteProvider';

export default function Footer() {
  const { site } = useSite();
  return <footer className="foot"><div><Brand /><p>Новые голоса. Новые миры. Кино, созданное с воображением.</p></div><div className="foot-right"><span>СМОТРИТЕ. ОТКРЫВАЙТЕ. ВДОХНОВЛЯЙТЕСЬ.</span><br />© {new Date().getFullYear()} {site.site_name}</div></footer>;
}
