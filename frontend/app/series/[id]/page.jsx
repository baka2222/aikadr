'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, watchUrl } from '../../../lib/api';
import { episodeCount } from '../../../lib/format';

export default function SeriesDetail() {
  const { id } = useParams();
  const [series, setSeries] = useState(null);
  const [season, setSeason] = useState(1);
  const [error, setError] = useState('');
  useEffect(() => { api(`/series/${id}`).then(setSeries).catch((err) => setError(err.message)); }, [id]);
  if (error) return <section className="page-intro"><h1>Сериал не найден</h1><p>{error}</p><Link className="button" href="/catalog">К каталогу</Link></section>;
  if (!series) return <section className="page-intro"><h1>Загрузка…</h1></section>;
  const seasons = [...new Set(series.episodes.map((episode) => episode.season))];
  const first = series.episodes[0];
  return <>
    <section className="detail-hero">
      {series.poster_url && <div className="detail-photo" style={{ backgroundImage: `url("${series.poster_url}")` }} />}
      <div className="detail-shade" />
      <div className="detail-inner"><div className="kicker">КАДР Original / {series.year}</div><h1>{series.title}</h1>
        <div className="hero-meta"><span>{series.year}</span><span>{series.genre}</span><span>{series.rating}</span><span>{episodeCount(series.episode_count)}</span></div>
        <p>{series.description}</p>
        <div className="hero-actions">{first && <Link className="button" href={watchUrl(series.id, first.id)}>▶ &nbsp; Смотреть серию 1</Link>}<Link className="button outline" href="/catalog">← Каталог</Link></div>
      </div>
    </section>
    <section className="content">
      <div className="episode-head"><h2>Эпизоды</h2>{seasons.length > 1 && <select className="select" value={season} onChange={(event) => setSeason(Number(event.target.value))} aria-label="Выбор сезона">{seasons.map((value) => <option key={value} value={value}>Сезон {value}</option>)}</select>}</div>
      {series.episodes.filter((episode) => episode.season === season).map((episode) => <Link className="episode" href={watchUrl(series.id, episode.id)} key={episode.id}>
        <div className="episode-thumb" style={{ backgroundImage: series.poster_url ? `url("${series.poster_url}")` : undefined }} />
        <div><div className="episode-num">СЕРИЯ {String(episode.number).padStart(2, '0')} · {episode.duration || 'Время не указано'}{episode.free_preview ? ' · БЕСПЛАТНО' : episode.has_video && !episode.can_watch ? ' · ПО ПОДПИСКЕ' : ''}</div><h3 className="episode-title">{episode.title}</h3><div className="episode-summary">{episode.description || series.description}</div></div>
        <div className="episode-play">{episode.has_video && !episode.can_watch ? '◇' : '▶'}</div>
      </Link>)}
      {!series.episodes.length && <div className="empty">Серии пока не добавлены.</div>}
    </section>
  </>;
}
