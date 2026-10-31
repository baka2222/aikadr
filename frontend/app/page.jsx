'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import PosterCard from '../components/PosterCard';
import Reveal from '../components/Reveal';
import { useSite } from '../components/SiteProvider';
import { api, seriesUrl, watchUrl } from '../lib/api';

export default function Home() {
  const { site } = useSite();
  const [shows, setShows] = useState([]);
  const [featured, setFeatured] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    api('/series').then(async (items) => {
      setShows(items);
      const lead = items.find((item) => item.featured) || items[0];
      if (lead) setFeatured(await api(`/series/${lead.id}`));
    }).catch((caught) => setError(caught.message)).finally(() => setLoading(false));
  }, []);
  const firstEpisode = featured?.episodes?.find((episode) => episode.has_video);
  const popular = shows.filter((show) => show.popular).slice(0, 5);
  const genres = [...new Set(shows.map((show) => show.genre))];
  return <>
    <section className={`cinema-hero ${site.hero_background_url ? 'has-backdrop' : ''}`}>
      {site.hero_background_url && <img className="cinema-backdrop" src={site.hero_background_url} alt="" fetchPriority="high" />}
      <div className="cinema-haze" aria-hidden="true" />
      {site.theme === 'winter' && <div className="season-sparkles" aria-hidden="true" />}
      <div className="cinema-copy"><div className="cinema-eyebrow"><span />{site.hero_kicker}</div>
        <h1>{site.hero_title}</h1><p>{site.hero_subtitle}</p>
        <div className="cinema-actions"><Link className="button" href={firstEpisode ? watchUrl(featured.id, firstEpisode.id) : '/catalog'}>{firstEpisode ? 'Начать просмотр' : 'Открыть каталог'}<span aria-hidden="true">↗</span></Link><Link className="button outline" href="/account">Мой аккаунт</Link></div>
        <div className="cinema-signature"><span className="signature-line" />Кино начинается с воображения.</div>
      </div>
      <div className="cinema-art">
        {featured ? <Link className="hero-feature" href={seriesUrl(featured.id)}>
          {featured.poster_url && <img src={featured.poster_url} alt={featured.title} fetchPriority="high" />}
          <div className="hero-feature-caption"><span>ВЫБОР РЕДАКЦИИ</span><h2>{featured.title}</h2><p>{featured.genre} · {featured.year}</p><b aria-hidden="true">↗</b></div>
        </Link> : <div className="brand-stage"><div className="brand-stage-ring" aria-hidden="true" />{site.logo_url && <img src={site.logo_url} alt={site.site_name} fetchPriority="high" />}<span>СОЗДАНО ВООБРАЖЕНИЕМ</span></div>}
      </div>
      <div className="cinema-bottom"><span>АВТОРСКИЕ ИСТОРИИ / AI CINEMA</span><a href="#discover">Листайте и открывайте <span aria-hidden="true">↓</span></a></div>
    </section>
    <section id="discover" className="content cinema-content"><Reveal>
      <div className="section-title"><div><div className="kicker">Ваша следующая история</div><h2>На экране</h2></div>{shows.length > 0 && <Link className="text-link" href="/catalog">Весь каталог ↗</Link>}</div>
      {loading ? <div className="poster-grid" aria-label="Загрузка каталога">{[1,2,3,4,5].map((i) => <div className="poster-skeleton" key={i} />)}</div> : error ? <div className="catalog-empty"><h3>Не удалось открыть каталог</h3><p>{error}</p><button className="button outline" onClick={() => window.location.reload()}>Попробовать ещё раз</button></div> : shows.length ? <div className="poster-grid">{shows.slice(0,5).map((show) => <PosterCard key={show.id} series={show} />)}</div> : <div className="catalog-empty"><div className="empty-reel" aria-hidden="true">▷</div><div><span className="kicker">ПЕРЕД ПРЕМЬЕРОЙ</span><h3>Новые миры готовятся к встрече</h3><p>Первые сериалы появятся здесь после публикации. Пока можно создать аккаунт — он пригодится для просмотра.</p><Link className="text-link" href="/account">Создать аккаунт ↗</Link></div></div>}
    </Reveal>
    {genres.length > 0 && <Reveal className="genre-discovery"><span className="kicker">Выберите настроение</span><div>{genres.map((genre) => <Link key={genre} href={`/catalog?genre=${encodeURIComponent(genre)}`}>{genre}<span>↗</span></Link>)}</div></Reveal>}
    {popular.length > 0 && <Reveal className="popular-section"><div className="section-title"><div><div className="kicker">Стоит посмотреть</div><h2>В центре внимания</h2></div></div><div className="poster-grid">{popular.map((show) => <PosterCard key={show.id} series={show} />)}</div></Reveal>}
    </section>
    <Reveal><section className="cinema-manifesto"><span className="manifesto-number" aria-hidden="true">ai</span><div><span className="kicker">ЗА КАЖДЫМ КАДРОМ — АВТОР</span><h2>Технологии меняются.<br /><em>Истории остаются.</em></h2><p>Мы собираем сериалы, созданные людьми с помощью искусственного интеллекта. Чтобы у новых голосов был свой экран, а у вас — новые впечатления.</p><Link className="text-link" href="/catalog">Найти свою историю ↗</Link></div></section></Reveal>
  </>;
}
