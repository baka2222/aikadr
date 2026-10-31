'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, uploadWithProgress } from '../../../../lib/api';
import './upload.css';

const size = (bytes) => bytes < 1024 ** 3 ? `${(bytes / 1024 ** 2).toFixed(1)} МБ` : `${(bytes / 1024 ** 3).toFixed(2)} ГБ`;

export default function VideoUpload() {
  const { episodeId } = useParams();
  const [info, setInfo] = useState(null);
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [state, setState] = useState('idle');
  const [error, setError] = useState('');
  useEffect(() => {
    api(`/admin/episodes/${episodeId}/upload-info`).then(setInfo).catch((caught) => setError(caught.message));
  }, [episodeId]);
  useEffect(() => {
    if (state !== 'uploading' && state !== 'saving') return;
    const warn = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [state]);

  const submit = async (event) => {
    event.preventDefault();
    if (!file || !info) return;
    const available = info.storage_quota_bytes == null ? Infinity : info.storage_quota_bytes - info.storage_used_bytes + info.video_size;
    if (file.size > info.max_video_bytes || file.size > available) {
      setError(file.size > info.max_video_bytes ? `Один файл не должен превышать ${size(info.max_video_bytes)}.` : 'Недостаточно места у автора. Освободите место или попросите супер-администратора увеличить лимит.');
      return;
    }
    setError(''); setProgress(0); setState('uploading');
    const body = new FormData(); body.append('file', file);
    try {
      await uploadWithProgress(`/admin/episodes/${episodeId}/video`, body, (value) => { setProgress(value); if (value === 100) setState('saving'); });
      setInfo(await api(`/admin/episodes/${episodeId}/upload-info`));
      setState('done');
    } catch (caught) { setError(caught.message); setState('idle'); }
  };

  const available = info?.storage_quota_bytes == null ? null : info.storage_quota_bytes - info.storage_used_bytes + info.video_size;
  return <main className="upload-page"><div className="upload-shell">
    <header className="upload-header"><Link href="/admin">← Вернуться в студию</Link><span>AIKADR / ЗАГРУЗКА ВИДЕО</span></header>
    <div className="upload-heading"><span className="upload-kicker">ОТДЕЛЬНОЕ ОКНО ЗАГРУЗКИ</span><h1>Новая сцена<br /><em>начинается здесь.</em></h1><p>Держите эту вкладку открытой до завершения. В другой вкладке можно продолжать работать с сайтом.</p></div>
    <section className="upload-card" aria-label="Загрузка видео">
      {!info && !error && <p role="status">Загружаем сведения об эпизоде…</p>}
      {info && <><div className="upload-episode"><span>СЕРИАЛ / СЕРИЯ</span><h2>{info.series_title}</h2><p>Сезон {info.season} · Серия {info.number} · {info.title}</p></div>
        {info.storage_quota_bytes != null && <div className="upload-storage"><div><span>МЕСТО АВТОРА</span><strong>{size(info.storage_used_bytes)} / {size(info.storage_quota_bytes)}</strong></div><progress value={Math.min(info.storage_used_bytes, info.storage_quota_bytes)} max={info.storage_quota_bytes} /><small>При замене старого видео его объём освобождается. Доступно для этого файла: {size(Math.max(0, available))}.</small></div>}
        <form onSubmit={submit}><label className="upload-file-label" htmlFor="episode-video">Видеофайл MP4 или WebM</label><input id="episode-video" type="file" accept="video/mp4,video/webm" disabled={state === 'uploading' || state === 'saving'} onChange={(event) => { setFile(event.target.files?.[0] || null); setError(''); setState('idle'); }} required />
          <p className="upload-hint">{file ? `${file.name} · ${size(file.size)}` : `Выберите файл до ${size(info.max_video_bytes)}.`}</p>
          {(state === 'uploading' || state === 'saving') && <div className="upload-progress" role="status" aria-live="polite"><div><strong>{state === 'saving' ? 'Сохраняем в базе данных…' : 'Передаём видео на сервер'}</strong><b>{progress}%</b></div><progress value={progress} max="100" /><small>{state === 'saving' ? 'Передача завершилась. Подождите подтверждения сохранения.' : 'Не закрывайте эту вкладку до подтверждения.'}</small></div>}
          {state === 'done' && <p className="upload-success" role="status">Видео сохранено. Обновите страницу сериала в студии, чтобы увидеть новый файл.</p>}
          <button className="upload-submit" type="submit" disabled={!file || state === 'uploading' || state === 'saving'}>{state === 'uploading' || state === 'saving' ? 'Загрузка идёт…' : info.video_size ? 'Заменить видео ↗' : 'Загрузить видео ↗'}</button>
        </form></>}
      {error && <p className="upload-error" role="alert">{error}</p>}
    </section><p className="upload-footnote">Файл сохраняется в PostgreSQL. Закрытие этой вкладки во время передачи прервёт загрузку.</p>
  </div></main>;
}
