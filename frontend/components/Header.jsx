'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import Brand from './Brand';

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const submit = (event) => {
    event.preventDefault();
    router.push(`/catalog${query.trim() ? `?search=${encodeURIComponent(query.trim())}` : ''}`);
    setOpen(false);
  };
  const active = (path) => pathname === path || (path === '/catalog' && pathname.startsWith('/series'));
  return <>
    <header className="top">
      <Brand />
      <nav className="nav" aria-label="Основная навигация">
        <Link className={active('/') ? 'active' : ''} href="/">Главная</Link>
        <Link className={active('/catalog') ? 'active' : ''} href="/catalog">Каталог</Link>
        <Link className={active('/pricing') ? 'active' : ''} href="/pricing">Подписка</Link>
        <Link className={active('/account') ? 'active' : ''} href="/account">Аккаунт</Link>
      </nav>
      <div className="header-right">
        <button className="icon-btn" aria-label="Открыть поиск" aria-expanded={open} aria-controls="search-panel" onClick={() => setOpen(!open)}>⌕</button>
        <Link className="top-cta" href="/pricing">Выбрать подписку ↗</Link>
      </div>
      <form id="search-panel" className={`search-wrap ${open ? 'open' : ''}`} role="search" onSubmit={submit}>
        <label className="sr-only" htmlFor="search-input">Поиск сериалов</label>
        <input id="search-input" type="search" placeholder="Название, описание или жанр..." value={query} onChange={(event) => setQuery(event.target.value)} />
        <button className="button min" type="submit">Найти</button>
      </form>
    </header>
    <nav className="mobile-dock" aria-label="Мобильная навигация">
      <Link className={active('/') ? 'active' : ''} href="/"><b>⌂</b>Главная</Link>
      <Link className={active('/catalog') ? 'active' : ''} href="/catalog"><b>▦</b>Каталог</Link>
      <Link className={active('/pricing') ? 'active' : ''} href="/pricing"><b>◇</b>Подписка</Link>
      <Link className={active('/account') ? 'active' : ''} href="/account"><b>○</b>Аккаунт</Link>
    </nav>
  </>;
}
