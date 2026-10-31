'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { api, seriesUrl, watchUrl } from '../../../../lib/api';

export default function Watch() {
  const { seriesId, episodeId } = useParams();
  const [series, setSeries] = useState(null);
  const [error, setError] = useState('');
  const [videoError, setVideoError] = useState(false);
  const sessionId = useRef(null);
  const timer = useRef(null);
  const playing = useRef(false);
  const starting = useRef(false);
  useEffect(() => {
    setVideoError(false);
    api(`/series/${seriesId}`).then(setSeries).catch((err) => setError(err.message));
    return () => {
      if (timer.current) clearInterval(timer.current);
      if (sessionId.current) api('/views/state', { method: 'POST', body: JSON.stringify({ session_id: sessionId.current, playing: false }) }).catch(() => {});
      sessionId.current = null;
    };
  }, [seriesId, episodeId]);
  const pauseTracking = () => {
    playing.current = false;
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
    if (sessionId.current) api('/views/state', { method: 'POST', body: JSON.stringify({ session_id: sessionId.current, playing: false }) }).catch(() => {});
  };
  const startTracking = async () => {
    playing.current = true;
    if (starting.current || timer.current) return;
    starting.current = true;
    try {
      if (!sessionId.current) {
        const result = await api('/views/start', { method: 'POST', body: JSON.stringify({ episode_id: episodeId }) });
        sessionId.current = result.session_id;
      } else {
        await api('/views/state', { method: 'POST', body: JSON.stringify({ session_id: sessionId.current, playing: true }) });
      }
      if (playing.current) timer.current = setInterval(() => {
        if (sessionId.current) api('/views/heartbeat', { method: 'POST', body: JSON.stringify({ session_id: sessionId.current }) }).catch(() => {});
      }, 15000);
      else if (sessionId.current) await api('/views/state', { method: 'POST', body: JSON.stringify({ session_id: sessionId.current, playing: false }) });
    } catch { /* Anonymous previews and staff playback do not accrue views. */ }
    finally { starting.current = false; }
  };
  if (error) return <section className="page-intro"><h1>Не удалось открыть видео</h1><p>{error}</p></section>;
  if (!series) return <section className="page-intro"><h1>Загрузка…</h1></section>;
  const index = series.episodes.findIndex((item) => item.id === episodeId);
  const episode = series.episodes[index];
  if (!episode) return <section className="page-intro"><h1>Серия не найдена</h1><Link className="button" href={seriesUrl(series.id)}>К сериалу</Link></section>;
  const previous = series.episodes[index - 1];
  const next = series.episodes[index + 1];
  return <>
    {episode.video_url && !videoError ? <div className="video-shell"><video key={episode.id} controls playsInline preload="metadata" poster={series.poster_url || undefined} onPlaying={startTracking} onPause={pauseTracking} onWaiting={pauseTracking} onEnded={pauseTracking} onError={() => setVideoError(true)}><source src={episode.video_url} />Ваш браузер не поддерживает видео.</video></div> : <div className="player-screen" style={{ backgroundImage: series.poster_url ? `url("${series.poster_url}")` : undefined }}><div className="player-center"><div className="kicker">КАДР / ПРОСМОТР</div><h1>{series.title}</h1><p>{episode.has_video && !episode.can_watch ? 'Для просмотра этой серии нужна подписка.' : videoError ? 'Не удалось загрузить видео. Попробуйте позже.' : 'Видео для этой серии пока не подключено.'}</p>{episode.has_video && !episode.can_watch && <Link className="button" href="/pricing">Выбрать подписку →</Link>}</div></div>}
    <section className="content watch-content">
      <div className="kicker">Сейчас смотрите</div><h1>{series.title}</h1><p className="subtle">Сезон {episode.season} · Серия {episode.number} · {episode.title}</p>
      <div className="hero-actions">
        <Link className="button outline" href={seriesUrl(series.id)}>← К эпизодам</Link>
        {previous && <Link className="button outline" href={watchUrl(series.id, previous.id)}>← Предыдущая</Link>}
        {next && <Link className="button" href={watchUrl(series.id, next.id)}>Следующая серия →</Link>}
      </div>
    </section>
  </>;
}
