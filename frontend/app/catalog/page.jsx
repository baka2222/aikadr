'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import PosterCard from '../../components/PosterCard';
import { api } from '../../lib/api';

function CatalogContent() {
  const params = useSearchParams();
  const router = useRouter();
  const search = params.get('search') || '';
  const genre = params.get('genre') || '';
  const sort = params.get('sort') || 'new';
  const [query, setQuery] = useState(search);
  const [shows, setShows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => setQuery(search), [search]);
  useEffect(() => {
    api('/categories').then(setCategories).catch((err) => setError(err.message));
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const request = new URLSearchParams({ search, genre, sort });
    api(`/series?${request}`, { signal: controller.signal }).then((items) => { setShows(items); setError(''); })
      .catch((err) => { if (err.name !== 'AbortError') setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, genre, sort]);
  const navigate = (changes) => {
    const next = new URLSearchParams({ search, genre, sort, ...changes });
    for (const [key, value] of [...next.entries()]) if (!value || (key === 'sort' && value === 'new')) next.delete(key);
    router.push(`/catalog${next.size ? `?${next}` : ''}`);
  };
  return <>
    <section className="page-intro"><div className="kicker">Каталог / все истории</div><h1>Все сериалы</h1><p className="subtle">Найдите историю по названию, жанру или настроению.</p></section>
    <div className="catalog-toolbar">
      <form className="catalog-search" onSubmit={(event) => { event.preventDefault(); navigate({ search: query }); }}>
        <label className="sr-only" htmlFor="catalog-query">Поиск по каталогу</label>
        <input id="catalog-query" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Название, описание или жанр" />
        <button className="button min" type="submit">Найти</button>
      </form>
      <select className="select" value={sort} onChange={(event) => navigate({ sort: event.target.value })} aria-label="Сортировка">
        <option value="new">Сначала новинки</option><option value="popular">Популярное</option>
      </select>
    </div>
    <div className="filters" aria-label="Фильтр по жанру">
      <button className={`chip ${!genre ? 'active' : ''}`} onClick={() => navigate({ genre: '' })}>Все</button>
      {categories.map((category) => <button key={category.id} className={`chip ${genre === category.name ? 'active' : ''}`} onClick={() => navigate({ genre: category.name })}>{category.name}</button>)}
    </div>
    <section className="content catalog-content">
      {loading ? <div className="empty" role="status">Открываем каталог…</div> : error ? <div className="empty" role="alert">{error}</div> : shows.length ? <div className="poster-grid">{shows.map((item) => <PosterCard key={item.id} series={item} />)}</div> : <div className="empty">{search || genre ? 'Ничего не нашлось. Попробуйте другой запрос или жанр.' : 'Первые истории готовятся к премьере. Загляните к нам чуть позже.'}</div>}
    </section>
  </>;
}

export default function Catalog() {
  return <Suspense fallback={<div className="page-intro"><h1>Каталог</h1><p className="subtle">Загрузка…</p></div>}><CatalogContent /></Suspense>;
}
