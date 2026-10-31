'use client';
import Link from 'next/link';
import { useSite } from './SiteProvider';

export default function Brand({ className = '' }) {
  const { site } = useSite();
  return <Link className={`site-brand ${className}`} href="/" aria-label={`${site.site_name} — главная`}>
    {site.logo_url && <img src={site.logo_url} alt="" width="54" height="54" />}
    <span>{site.site_name}<small>ИСТОРИИ НОВОГО ВРЕМЕНИ</small></span>
  </Link>;
}
