'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, seriesUrl } from '../../lib/api';
import AuthForm from '../../components/AuthForm';
import Brand from '../../components/Brand';
import { useSite } from '../../components/SiteProvider';
import { AppearancePanel, TeamPanel, VideoLibrary } from '../../components/StudioExtras';
import './studio.css';
import './studio-premium.css';

const monthNow = () => new Date().toISOString().slice(0, 7);
const money = (value = 0) => new Intl.NumberFormat('ru-RU').format(value);
const date = (stamp) => stamp ? new Date(stamp * 1000).toLocaleDateString('ru-RU') : '—';
const emptyShow = (categoryId = '') => ({
  title: '', description: '', category_id: categoryId, poster_url: '', year: new Date().getFullYear(),
  rating: '12+', featured: false, popular: false, owner_id: null, is_published: true,
});
const emptyEpisode = () => ({ season: 1, number: 1, title: '', description: '', duration: '', video_url: '', free_preview: false });

function Notice({ error, message }) {
  return <>{error && <div className="studio-notice error" role="alert">{error}</div>}{message && <div className="studio-notice success" role="status">{message}</div>}</>;
}

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const run = async (task, success = '') => {
    setBusy(true); setError(''); setMessage('');
    try { const result = await task(); setMessage(success); return result; }
    catch (caught) { setError(caught.message); return null; }
    finally { setBusy(false); }
  };
  return { busy, error, message, run };
}

function Bars({ points = [] }) {
  const max = Math.max(1, ...points.map((point) => point.views));
  return <div className="studio-bars" aria-label="Просмотры по дням">
    {points.length ? points.map((point) => <div className="studio-bar-slot" key={point.day} title={`${point.day}: ${point.views}`}>
      <div className="studio-bar" style={{ height: `${Math.max(7, point.views / max * 100)}%` }} />
      <span>{point.day.slice(8)}</span>
    </div>) : <div className="studio-empty-chart">Просмотры появятся здесь после запуска сериала.</div>}
  </div>;
}

function Dashboard({ user, month }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api(`/admin/dashboard?month=${month}`).then(setData).catch((caught) => setError(caught.message));
  }, [month]);
  if (error) return <div className="studio-notice error">{error}</div>;
  if (!data) return <div className="studio-loading">Загружаем показатели…</div>;
  if (data.role === 'moderator') return <><div className="studio-section-heading"><div><span className="studio-eyebrow">КАТАЛОГ И МЕДИАТЕКА</span><h2>Рабочее пространство модератора</h2></div></div><div className="studio-kpis">{[['Сериалы',data.series_count],['Опубликовано',data.published_count],['Загруженные видео',data.video_count]].map(([label,value]) => <article key={label} className="studio-kpi"><span>{label}</span><strong>{value}</strong></article>)}</div><section className="studio-panel"><p className="studio-muted">Проверяйте материалы, редактируйте сериалы и управляйте видео. Финансы и права пользователей доступны супер-администраторам.</p></section></>;
  const owner = user.role === 'superadmin';
  const cards = owner
    ? [
      ['Выручка месяца', `${money(data.finance.revenue_som)} сом`, 'По подтверждённым заявкам или ручной корректировке'],
      ['Доля владельца', `${money(data.finance.owner_share_som)} сом`, `${data.finance.owner_percent}% от выручки`],
      ['Авторам', `${money(data.finance.author_pool_som)} сом`, `${data.finance.author_percent}% распределяется по просмотрам`],
      ['Заявки на проверке', data.pending_payments, 'Подтверждение оплаты вручную'],
    ]
    : [
      ['Начислено за месяц', `${money(data.earned_som)} сом`, data.payout ? 'Выплата отмечена владельцем' : 'Выплата ожидает решения владельца'],
      ['Подтверждённые просмотры', money(data.views), 'Один зритель на серию в день'],
      ['Мои сериалы', data.series_count, 'Контент в вашем кабинете'],
    ];
  return <>
    <div className="studio-section-heading"><div><span className="studio-eyebrow">АНАЛИТИКА / {month}</span><h2>{owner ? 'Вся картина за месяц' : 'Ваши результаты'}</h2></div><span className="studio-live"><i /> Данные обновляются</span></div>
    <div className="studio-kpis">{cards.map(([label, value, hint]) => <article className="studio-kpi" key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></article>)}</div>
    <div className="studio-two">
      <section className="studio-panel"><div className="studio-panel-top"><div><span className="studio-eyebrow">ДИНАМИКА</span><h3>Просмотры по дням</h3></div><span className="studio-muted">{owner ? data.finance.total_views : data.views} за месяц</span></div><Bars points={data.daily_views} /></section>
      <section className="studio-panel"><div className="studio-panel-top"><div><span className="studio-eyebrow">{owner ? 'РАСПРЕДЕЛЕНИЕ' : 'ВАШ КАТАЛОГ'}</span><h3>{owner ? 'Авторы' : 'Сериалы'}</h3></div></div>
        <div className="studio-rank">{owner ? data.finance.authors.map((item, index) => <div key={item.author_id}><b>{String(index + 1).padStart(2, '0')}</b><span><strong>{item.full_name}</strong><small>{item.views} просмотров</small></span><em>{money(item.earned_som)} сом</em></div>)
          : data.shows.map((item, index) => <div key={item.id}><b>{String(index + 1).padStart(2, '0')}</b><span><strong>{item.title}</strong><small>Сериал</small></span><em>{item.views} просмотров</em></div>)}
          {!(owner ? data.finance.authors.length : data.shows.length) && <p className="studio-muted">Пока нет данных.</p>}
        </div>
      </section>
    </div>
  </>;
}

function Catalog({ user }) {
  const [shows, setShows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [authors, setAuthors] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState(emptyShow());
  const [episodeId, setEpisodeId] = useState(null);
  const [episodeForm, setEpisodeForm] = useState(emptyEpisode());
  const action = useAction();
  const load = async () => {
    const requests = [api('/admin/series'), api('/categories')];
    if (user.role === 'superadmin') requests.push(api('/admin/users'));
    const [nextShows, nextCategories, nextUsers = []] = await Promise.all(requests);
    setShows(nextShows); setCategories(nextCategories);
    setAuthors(nextUsers.filter((item) => item.role === 'author'));
    return { nextShows, nextCategories };
  };
  useEffect(() => { load().catch(() => {}); }, []);
  const open = async (id) => {
    setSelected(id); setEpisodeId(null); setEpisodeForm(emptyEpisode());
    if (id === 'new') { setDetail(null); setForm(emptyShow(categories[0]?.id || '')); return; }
    const item = await action.run(() => api(`/admin/series/${id}`));
    if (!item) return;
    setDetail(item);
    setForm({
      title: item.title, description: item.description, category_id: item.category_id, poster_url: item.poster_url,
      year: item.year, rating: item.rating, featured: item.featured, popular: item.popular,
      owner_id: item.owner_id, is_published: item.is_published,
    });
  };
  const saveShow = (event) => {
    event.preventDefault();
    action.run(async () => {
      const item = await api(selected === 'new' ? '/admin/series' : `/admin/series/${selected}`, {
        method: selected === 'new' ? 'POST' : 'PUT', body: JSON.stringify(form),
      });
      await load(); setSelected(item.id); setDetail(item);
    }, 'Сериал сохранён');
  };
  const removeShow = () => {
    if (!confirm('Удалить сериал вместе со всеми сериями и видео?')) return;
    action.run(async () => { await api(`/admin/series/${selected}`, { method: 'DELETE' }); await load(); setSelected(null); setDetail(null); }, 'Сериал удалён');
  };
  const uploadCover = (file) => {
    if (!file) return;
    action.run(async () => { const body = new FormData(); body.append('file', file); const result = await api('/admin/covers', { method: 'POST', body }); setForm((current) => ({ ...current, poster_url: result.url })); }, 'Обложка загружена');
  };
  const saveEpisode = (event) => {
    event.preventDefault();
    action.run(async () => {
      await api(episodeId ? `/admin/episodes/${episodeId}` : `/admin/series/${selected}/episodes`, {
        method: episodeId ? 'PUT' : 'POST', body: JSON.stringify(episodeForm),
      });
      const item = await api(`/admin/series/${selected}`);
      setDetail(item); setEpisodeId(null); setEpisodeForm({ ...emptyEpisode(), number: (item.episodes.at(-1)?.number || 0) + 1 });
      await load();
    }, 'Серия сохранена');
  };
  const editEpisode = (episode) => {
    setEpisodeId(episode.id);
    setEpisodeForm({ season: episode.season, number: episode.number, title: episode.title,
      description: episode.description, duration: episode.duration, video_url: episode.source_video_url || '', free_preview: episode.free_preview });
    document.getElementById('studio-episode-editor')?.scrollIntoView({ behavior: 'smooth' });
  };
  const removeEpisode = (id) => {
    if (!confirm('Удалить серию и загруженное видео?')) return;
    action.run(async () => { await api(`/admin/episodes/${id}`, { method: 'DELETE' }); setDetail(await api(`/admin/series/${selected}`)); }, 'Серия удалена');
  };
  return <>
    <div className="studio-section-heading"><div><span className="studio-eyebrow">КОНТЕНТ</span><h2>{user.role === 'author' ? 'Мои сериалы' : 'Каталог платформы'}</h2></div><button className="studio-primary" onClick={() => open('new')}>＋ Новый сериал</button></div>
    <Notice {...action} />
    <div className="studio-catalog">
      <aside className="studio-list"><div className="studio-list-title">Сериалы <span>{shows.length}</span></div>
        {shows.map((item) => <button key={item.id} className={`studio-list-item ${selected === item.id ? 'active' : ''}`} onClick={() => open(item.id)}>
          <span className="studio-list-dot" /><span><strong>{item.title}</strong><small>{item.genre} · {item.episode_count} серий · {item.is_published ? 'Опубликован' : 'Черновик'}</small></span>
        </button>)}{!shows.length && <p className="studio-muted studio-pad">Добавьте первый сериал.</p>}
      </aside>
      <section className="studio-panel studio-editor">
        {!selected ? <div className="studio-blank"><span className="studio-eyebrow">ВАША СТУДИЯ</span><h3>История начинается здесь.</h3><p>Выберите сериал слева или создайте новый. Обложки, эпизоды и видео управляются в одной карточке.</p><button className="studio-primary" onClick={() => open('new')}>Создать сериал ↗</button></div> : <>
          <div className="studio-panel-top"><div><span className="studio-eyebrow">{selected === 'new' ? 'НОВЫЙ МАТЕРИАЛ' : 'РЕДАКТИРОВАНИЕ'}</span><h3>{selected === 'new' ? 'Новый сериал' : detail?.title}</h3></div>{detail && <Link className="studio-text-button" href={seriesUrl(detail.id)} target="_blank">Открыть на сайте ↗</Link>}</div>
          <form className="studio-form" onSubmit={saveShow}>
            <div className="studio-form-grid"><label>Название<input required maxLength={160} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
              <label>Жанр<select required value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}><option value="">Выберите жанр</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
            <label>Описание<textarea required rows={4} maxLength={3000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
            <div className="studio-form-grid"><label>Год<input required type="number" min="1900" max="2100" value={form.year} onChange={(e) => setForm({ ...form, year: Number(e.target.value) })} /></label>
              <label>Возрастной рейтинг<input value={form.rating} onChange={(e) => setForm({ ...form, rating: e.target.value })} /></label></div>
            {user.role === 'superadmin' && <label>Автор<select value={form.owner_id || ''} onChange={(e) => setForm({ ...form, owner_id: e.target.value || null })}><option value="">Без автора</option>{authors.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></label>}
            <label>Ссылка на обложку<input value={form.poster_url} onChange={(e) => setForm({ ...form, poster_url: e.target.value })} placeholder="https://... или /media/..." /></label>
            <label className="studio-upload">↑ Загрузить обложку<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => uploadCover(e.target.files?.[0])} /></label>
            {form.poster_url && <img className="studio-cover" src={form.poster_url} alt="Предпросмотр обложки" />}
            <div className="studio-checks"><label><input type="checkbox" checked={form.is_published} onChange={(e) => setForm({ ...form, is_published: e.target.checked })} /> Опубликован</label><label><input type="checkbox" checked={form.featured} onChange={(e) => setForm({ ...form, featured: e.target.checked })} /> На главном баннере</label><label><input type="checkbox" checked={form.popular} onChange={(e) => setForm({ ...form, popular: e.target.checked })} /> Популярное</label></div>
            <div className="studio-actions"><button className="studio-primary" disabled={action.busy} type="submit">Сохранить сериал</button>{selected !== 'new' && <button className="studio-danger" type="button" onClick={removeShow}>Удалить</button>}</div>
          </form>
          {detail && <div className="studio-episodes"><div className="studio-panel-top"><div><span className="studio-eyebrow">СЕЗОНЫ И СЕРИИ</span><h3>Эпизоды</h3></div><span className="studio-muted">{detail.episodes.length} шт.</span></div>
            {detail.episodes.map((episode) => <div className="studio-episode-row" key={episode.id}><div><strong>С{episode.season} · Э{episode.number} — {episode.title}</strong><small>{episode.has_video ? `Видео подключено${episode.video_size ? ` · ${Math.round(episode.video_size / 1024 / 1024)} МБ` : ''}` : 'Без видео'}{episode.free_preview ? ' · Бесплатный просмотр' : ''}</small></div>
              <div className="studio-episode-tools"><Link className="studio-text-button" href={`/admin/upload/${episode.id}`} target="_blank" rel="noopener">↑ Загрузить видео ↗</Link><button className="studio-text-button" onClick={() => editEpisode(episode)}>Изменить</button><button className="studio-text-button danger" onClick={() => removeEpisode(episode.id)}>Удалить</button></div></div>)}
            <form id="studio-episode-editor" className="studio-form studio-episode-form" onSubmit={saveEpisode}><span className="studio-eyebrow">{episodeId ? 'РЕДАКТИРОВАНИЕ СЕРИИ' : 'НОВАЯ СЕРИЯ'}</span><h3>{episodeId ? 'Изменить эпизод' : 'Добавить эпизод'}</h3>
              <div className="studio-form-grid"><label>Сезон<input type="number" min="1" max="99" required value={episodeForm.season} onChange={(e) => setEpisodeForm({ ...episodeForm, season: Number(e.target.value) })} /></label><label>Номер<input type="number" min="1" max="999" required value={episodeForm.number} onChange={(e) => setEpisodeForm({ ...episodeForm, number: Number(e.target.value) })} /></label></div>
              <label>Название<input required value={episodeForm.title} onChange={(e) => setEpisodeForm({ ...episodeForm, title: e.target.value })} /></label>
              <label>Описание<textarea rows={2} value={episodeForm.description} onChange={(e) => setEpisodeForm({ ...episodeForm, description: e.target.value })} /></label>
              <div className="studio-form-grid"><label>Длительность<input placeholder="22 мин" value={episodeForm.duration} onChange={(e) => setEpisodeForm({ ...episodeForm, duration: e.target.value })} /></label><label>Внешняя ссылка (только бесплатная серия)<input placeholder="https://.../video.mp4" value={episodeForm.video_url} onChange={(e) => setEpisodeForm({ ...episodeForm, video_url: e.target.value })} /></label></div>
              <div className="studio-checks"><label><input type="checkbox" checked={episodeForm.free_preview} onChange={(e) => setEpisodeForm({ ...episodeForm, free_preview: e.target.checked })} /> Бесплатный эпизод</label></div>
              <p className="studio-muted">Сначала сохраните эпизод, затем загрузите MP4/WebM в его строке выше. Максимум 2 ГБ на файл.</p>
              <div className="studio-actions"><button className="studio-primary" disabled={action.busy} type="submit">{episodeId ? 'Сохранить серию' : 'Добавить серию'}</button>{episodeId && <button className="studio-secondary" type="button" onClick={() => { setEpisodeId(null); setEpisodeForm(emptyEpisode()); }}>Отмена</button>}</div>
            </form>
          </div>}
        </>}
      </section>
    </div>
  </>;
}

function Finance({ month }) {
  const [report, setReport] = useState(null);
  const [form, setForm] = useState({ revenue_override_som: '', author_percent: 80, note: '' });
  const action = useAction();
  const load = () => api(`/admin/finance/${month}`).then((data) => {
    setReport(data); setForm({ revenue_override_som: data.revenue_overridden ? data.revenue_som : '',
      author_percent: data.author_percent, note: data.note });
  });
  useEffect(() => { load().catch(() => {}); }, [month]);
  const save = (event) => {
    event.preventDefault();
    action.run(async () => {
      const data = await api(`/admin/finance/${month}`, { method: 'PUT',
        body: JSON.stringify({ revenue_override_som: form.revenue_override_som === '' ? null : Number(form.revenue_override_som),
          author_percent: Number(form.author_percent), note: form.note }) });
      setReport(data);
    }, 'Параметры месяца сохранены');
  };
  const paid = (item) => {
    if (!confirm(`Отметить выплату ${money(item.earned_som)} сом автору ${item.full_name}? Деньги переводятся отдельно.`)) return;
    action.run(async () => { await api('/admin/payouts', { method: 'POST',
      body: JSON.stringify({ author_id: item.author_id, month, note: '' }) }); await load(); }, 'Выплата отмечена');
  };
  if (!report) return <div className="studio-loading">Считаем распределение…</div>;
  return <>
    <div className="studio-section-heading"><div><span className="studio-eyebrow">ФИНАНСЫ / {month}</span><h2>Распределение дохода</h2></div><span className="studio-live"><i /> Прозрачный расчёт</span></div>
    <Notice {...action} />
    <div className="studio-kpis">
      <article className="studio-kpi"><span>Оплачено подписок</span><strong>{money(report.actual_revenue_som)} сом</strong><small>Подтверждено в этом месяце</small></article>
      <article className="studio-kpi"><span>В расчёте</span><strong>{money(report.revenue_som)} сом</strong><small>{report.revenue_overridden ? 'Сумма скорректирована вручную' : 'Совпадает с оплатами'}</small></article>
      <article className="studio-kpi"><span>Фонд авторов</span><strong>{money(report.author_pool_som)} сом</strong><small>{report.author_percent}% от суммы в расчёте</small></article>
      <article className="studio-kpi"><span>Владельцу</span><strong>{money(report.owner_share_som)} сом</strong><small>{report.owner_percent}% от суммы в расчёте</small></article>
    </div>
    <div className="studio-two">
      <section className="studio-panel"><div className="studio-panel-top"><div><span className="studio-eyebrow">ПРАВИЛО МЕСЯЦА</span><h3>Настройка долей</h3></div></div>
        <form className="studio-form" onSubmit={save}>
          <label>Выручка для распределения, сом<input type="number" min="0" placeholder={`Автоматически: ${report.actual_revenue_som}`} value={form.revenue_override_som} onChange={(e) => setForm({ ...form, revenue_override_som: e.target.value })} /></label>
          <p className="studio-muted">Оставьте поле пустым, чтобы брать сумму подтверждённых подписок. Ручная сумма влияет на расчёт, но не меняет платежи.</p>
          <label>Авторам, %<input type="number" min="0" max="100" value={form.author_percent} onChange={(e) => setForm({ ...form, author_percent: e.target.value })} /></label>
          <div className="studio-split"><span>Авторам: {form.author_percent || 0}%</span><span>Владельцу: {100 - Number(form.author_percent || 0)}%</span></div>
          <label>Комментарий<textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Причина корректировки или примечание" /></label>
          <button className="studio-primary" type="submit" disabled={action.busy || report.authors.some((item) => item.payout)}>Сохранить расчёт</button>
          {report.authors.some((item) => item.payout) && <p className="studio-muted">После первой отмеченной выплаты расчёт месяца зафиксирован.</p>}
        </form>
      </section>
      <section className="studio-panel"><div className="studio-panel-top"><div><span className="studio-eyebrow">МЕТОДИКА</span><h3>Как считаются деньги</h3></div></div>
        <div className="studio-steps"><p><b>01</b><span>Оплаты, подтверждённые в этом месяце, формируют выручку. Сумму можно скорректировать вручную.</span></p><p><b>02</b><span>Процент авторов создаёт общий фонд. Остальное — доля владельца.</span></p><p><b>03</b><span>Фонд делится между авторами пропорционально их подтверждённым просмотрам за месяц.</span></p><p><b>04</b><span>После окончания месяца владелец переводит деньги вне сайта и отмечает выплату здесь.</span></p></div>
      </section>
    </div>
    <section className="studio-panel studio-table-panel"><div className="studio-panel-top"><div><span className="studio-eyebrow">ВЕДОМОСТЬ</span><h3>Кому сколько перевести</h3></div><span className="studio-muted">{report.total_views} просмотров{report.unallocated_som ? ` · ${money(report.unallocated_som)} сом ожидают просмотров` : ''}</span></div>
      <div className="studio-table-wrap"><table className="studio-table"><thead><tr><th>Автор</th><th>Просмотры</th><th>Доля</th><th>К выплате</th><th>Статус</th></tr></thead><tbody>
        {report.authors.map((item) => <tr key={item.author_id}><td><strong>{item.full_name}</strong><small>{item.email}</small></td><td>{money(item.views)}</td><td>{report.total_views ? (item.views / report.total_views * 100).toFixed(1) : '0'}%</td><td><strong>{money(item.earned_som)} сом</strong></td><td>{item.payout ? <span className="studio-pill done">Переведено {date(item.payout.paid_at)}</span> : <button className="studio-small-button" onClick={() => paid(item)} disabled={action.busy || !item.earned_som || month >= monthNow()}>Отметить выплату</button>}</td></tr>)}
        {!report.authors.length && <tr><td colSpan="5" className="studio-muted">Создайте авторов, чтобы появилась ведомость.</td></tr>}
      </tbody></table></div>{month >= monthNow() && <p className="studio-muted">Выплату можно отметить после окончания выбранного месяца.</p>}
    </section>
  </>;
}

function Payments() {
  const [requests, setRequests] = useState([]);
  const action = useAction();
  const load = () => api('/admin/payment-requests').then(setRequests);
  useEffect(() => { load().catch(() => {}); }, []);
  const review = (item, decision) => {
    if (decision === 'approved' && !confirm('Вы сверили поступление денег на карту? Подтвердить подписку?')) return;
    action.run(async () => { await api(`/admin/payment-requests/${item.id}/review`, {
      method: 'POST', body: JSON.stringify({ decision, note: '' }),
    }); await load(); }, decision === 'approved' ? 'Подписка активирована' : 'Заявка отклонена');
  };
  const pending = requests.filter((item) => item.status === 'pending');
  return <>
    <div className="studio-section-heading"><div><span className="studio-eyebrow">ПОДПИСКИ</span><h2>Проверка оплат</h2></div><span className="studio-badge">{pending.length} ожидают</span></div>
    <Notice {...action} />
    <div className="studio-payment-grid">{requests.map((item) => <article className="studio-payment-card" key={item.id}>
      <div className="studio-payment-top"><span className={`studio-pill ${item.status === 'approved' ? 'done' : item.status === 'rejected' ? 'rejected' : 'waiting'}`}>{item.status === 'pending' ? 'На проверке' : item.status === 'approved' ? 'Подтверждено' : 'Отклонено'}</span><span className="studio-muted">{date(item.created_at)}</span></div>
      <h3>{money(item.price_som)} сом</h3><p>{item.plan_title}{item.payment_method_title ? ` · ${item.payment_method_title}` : ''}</p><strong>{item.full_name}</strong><small>{item.email}</small>
      <div className="studio-actions"><a className="studio-secondary" href={`/api/admin/payment-requests/${item.id}/receipt`} target="_blank" rel="noreferrer">Открыть чек ↗</a>{item.status === 'pending' && <><button className="studio-primary" disabled={action.busy} onClick={() => review(item, 'approved')}>Подтвердить</button><button className="studio-danger" disabled={action.busy} onClick={() => review(item, 'rejected')}>Отклонить</button></>}</div>
    </article>)}{!requests.length && <div className="studio-panel studio-blank"><h3>Заявок пока нет</h3><p>После загрузки чека зрителем заявка появится здесь и в Telegram, если бот подключён.</p></div>}</div>
  </>;
}

function Plans() {
  const [plans, setPlans] = useState([]);
  const [methods, setMethods] = useState([]);
  const [methodSelected, setMethodSelected] = useState('new');
  const [methodForm, setMethodForm] = useState({ title: '', details: '', active: true, sort_order: 0 });
  const [selected, setSelected] = useState('new');
  const [form, setForm] = useState({ title: '', description: '', price_som: 0, duration_days: 30, active: true, sort_order: 0 });
  const [settings, setSettings] = useState({ payment_instructions: '', default_author_percent: 80 });
  const action = useAction();
  const load = async () => {
    const [nextPlans, nextSettings, nextMethods] = await Promise.all([api('/admin/plans'), api('/admin/settings'), api('/admin/payment-methods')]);
    setPlans(nextPlans); setSettings(nextSettings); setMethods(nextMethods);
  };
  useEffect(() => { load().catch(() => {}); }, []);
  const choose = (item) => {
    setSelected(item?.id || 'new');
    setForm(item ? { title: item.title, description: item.description, price_som: item.price_som, duration_days: item.duration_days,
      active: item.active, sort_order: item.sort_order } : { title: '', description: '', price_som: 0, duration_days: 30, active: true, sort_order: 0 });
  };
  const savePlan = (event) => {
    event.preventDefault();
    action.run(async () => {
      const item = await api(selected === 'new' ? '/admin/plans' : `/admin/plans/${selected}`, {
        method: selected === 'new' ? 'POST' : 'PUT', body: JSON.stringify({ ...form, price_som: Number(form.price_som), duration_days: Number(form.duration_days), sort_order: Number(form.sort_order) }),
      });
      await load(); choose(item);
    }, 'Тариф сохранён');
  };
  const remove = () => {
    if (!confirm('Удалить тариф? Тариф с существующими заявками можно только отключить.')) return;
    action.run(async () => { await api(`/admin/plans/${selected}`, { method: 'DELETE' }); await load(); choose(null); }, 'Тариф удалён');
  };
  const saveSettings = (event) => {
    event.preventDefault();
    action.run(async () => { await api('/admin/settings', { method: 'PUT', body: JSON.stringify({
      ...settings, default_author_percent: Number(settings.default_author_percent),
    }) }); await load(); }, 'Реквизиты и правило по умолчанию сохранены');
  };
  const chooseMethod = (item) => {
    setMethodSelected(item?.id || 'new');
    setMethodForm(item ? { title: item.title, details: item.details, active: item.active, sort_order: item.sort_order } : { title: '', details: '', active: true, sort_order: 0 });
  };
  const saveMethod = (event) => {
    event.preventDefault();
    action.run(async () => {
      const item = await api(methodSelected === 'new' ? '/admin/payment-methods' : `/admin/payment-methods/${methodSelected}`, {
        method: methodSelected === 'new' ? 'POST' : 'PUT', body: JSON.stringify({ ...methodForm, sort_order: Number(methodForm.sort_order) }),
      });
      await load(); chooseMethod(item);
    }, 'Способ оплаты сохранён');
  };
  const removeMethod = () => {
    if (!confirm('Удалить способ оплаты? Старые заявки сохранят название способа.')) return;
    action.run(async () => { await api(`/admin/payment-methods/${methodSelected}`, { method: 'DELETE' }); await load(); chooseMethod(null); }, 'Способ оплаты удалён');
  };
  return <>
    <div className="studio-section-heading"><div><span className="studio-eyebrow">МОНЕТИЗАЦИЯ</span><h2>Тарифы и реквизиты</h2></div><button className="studio-primary" onClick={() => choose(null)}>＋ Новый тариф</button></div>
    <Notice {...action} />
    <div className="studio-two"><section className="studio-panel"><div className="studio-panel-top"><div><span className="studio-eyebrow">ПЛАНЫ ПОДПИСКИ</span><h3>{selected === 'new' ? 'Создать тариф' : 'Редактировать тариф'}</h3></div></div>
      <div className="studio-plan-list">{plans.map((item) => <button className={selected === item.id ? 'active' : ''} key={item.id} onClick={() => choose(item)}><span><strong>{item.title}</strong><small>{item.duration_days} дней · {item.active ? 'Активен' : 'Выключен'}</small></span><b>{money(item.price_som)} сом</b></button>)}</div>
      <form className="studio-form" onSubmit={savePlan}><label>Название<input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label><label>Описание<textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <div className="studio-form-grid"><label>Цена, сом<input type="number" min="0" required value={form.price_som} onChange={(e) => setForm({ ...form, price_som: e.target.value })} /></label><label>Дней доступа<input type="number" min="1" required value={form.duration_days} onChange={(e) => setForm({ ...form, duration_days: e.target.value })} /></label></div>
        <label>Порядок показа<input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })} /></label>
        <div className="studio-checks"><label><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Доступен зрителям</label></div>
        <div className="studio-actions"><button className="studio-primary" type="submit" disabled={action.busy}>Сохранить тариф</button>{selected !== 'new' && <button className="studio-danger" type="button" onClick={remove}>Удалить</button>}</div>
      </form>
    </section><section className="studio-panel"><div className="studio-panel-top"><div><span className="studio-eyebrow">РУЧНАЯ ОПЛАТА</span><h3>Инструкция зрителю</h3></div></div>
      <form className="studio-form" onSubmit={saveSettings}><label>Общая инструкция для зрителя<textarea required minLength={10} rows={7} value={settings.payment_instructions} onChange={(e) => setSettings({ ...settings, payment_instructions: e.target.value })} placeholder="Например: выберите способ оплаты ниже, переведите сумму и загрузите чек" /></label>
        <p className="studio-muted">Чтобы появилось поле загрузки чека, ниже добавьте хотя бы один активный способ оплаты. Одной общей инструкции недостаточно.</p>
        <label>Доля авторов по умолчанию, %<input type="number" min="0" max="100" value={settings.default_author_percent} onChange={(e) => setSettings({ ...settings, default_author_percent: e.target.value })} /></label>
        <p className="studio-muted">Для каждого месяца долю можно изменить в разделе «Финансы».</p>
        <button className="studio-primary" type="submit" disabled={action.busy}>Сохранить настройки</button>
      </form>
    </section></div>
    <section className="studio-panel studio-narrow"><div className="studio-panel-top"><div><span className="studio-eyebrow">СПОСОБЫ ОПЛАТЫ</span><h3>Куда зрителю перевести деньги</h3></div><button type="button" className="studio-secondary" onClick={() => chooseMethod(null)}>Новый способ +</button></div>
      {!methods.some((item) => item.active) && <p className="studio-notice error" role="status">Приём чеков пока закрыт. Создайте активный способ оплаты и сохраните общую инструкцию выше.</p>}
      <p className="studio-muted">Добавьте карту Visa, банковский перевод или другой способ с реальными реквизитами. Зритель выберет способ и приложит чек; подтвердить поступление можно в панели или Telegram-боте.</p>
      <div className="studio-plan-list">{methods.map((item) => <button type="button" className={methodSelected === item.id ? 'active' : ''} key={item.id} onClick={() => chooseMethod(item)}><span><strong>{item.title}</strong><small>{item.active ? 'Доступен зрителям' : 'Отключён'}</small></span></button>)}</div>
      <form className="studio-form" onSubmit={saveMethod}><label>Название способа<input required minLength={2} maxLength={120} value={methodForm.title} onChange={(e) => setMethodForm({ ...methodForm, title: e.target.value })} placeholder="Например, Visa" /></label><label>Реквизиты и инструкция<textarea required minLength={5} maxLength={1500} rows={4} value={methodForm.details} onChange={(e) => setMethodForm({ ...methodForm, details: e.target.value })} placeholder="Укажите реальные реквизиты и получателя" /></label><label>Порядок показа<input type="number" value={methodForm.sort_order} onChange={(e) => setMethodForm({ ...methodForm, sort_order: e.target.value })} /></label><div className="studio-checks"><label><input type="checkbox" checked={methodForm.active} onChange={(e) => setMethodForm({ ...methodForm, active: e.target.checked })} /> Показывать зрителям</label></div><div className="studio-actions"><button className="studio-primary" type="submit" disabled={action.busy}>Сохранить способ</button>{methodSelected !== 'new' && <button className="studio-danger" type="button" onClick={removeMethod} disabled={action.busy}>Удалить</button>}</div></form>
    </section>
  </>;
}

function Categories() {
  const [categories, setCategories] = useState([]);
  const [newName, setNewName] = useState('');
  const action = useAction();
  const load = () => api('/categories').then(setCategories);
  useEffect(() => { load().catch(() => {}); }, []);
  const create = (event) => {
    event.preventDefault();
    action.run(async () => { await api('/admin/categories', { method: 'POST', body: JSON.stringify({ name: newName }) }); setNewName(''); await load(); }, 'Жанр добавлен');
  };
  const remove = (item) => {
    if (!confirm(`Удалить жанр «${item.name}»?`)) return;
    action.run(async () => { await api(`/admin/categories/${item.id}`, { method: 'DELETE' }); await load(); }, 'Жанр удалён');
  };
  return <>
    <div className="studio-section-heading"><div><span className="studio-eyebrow">СТРУКТУРА КАТАЛОГА</span><h2>Жанры</h2></div></div><Notice {...action} />
    <section className="studio-panel studio-narrow"><form className="studio-inline-form" onSubmit={create}><input required placeholder="Название нового жанра" value={newName} onChange={(e) => setNewName(e.target.value)} /><button className="studio-primary">＋ Добавить</button></form>
      {categories.map((item) => <div className="studio-category-row" key={item.id}><strong>{item.name}</strong><button className="studio-text-button danger" onClick={() => remove(item)}>Удалить</button></div>)}
      <p className="studio-muted">Жанр с привязанными сериалами удалить нельзя.</p>
    </section>
  </>;
}

function Security({ user }) {
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const action = useAction();
  const save = (event) => {
    event.preventDefault();
    if (form.new_password !== form.confirm_password) {
      action.run(() => { throw new Error('Новые пароли не совпадают'); });
      return;
    }
    action.run(async () => {
      await api('/auth/change-password', { method: 'POST', body: JSON.stringify({
        current_password: form.current_password, new_password: form.new_password,
      }) });
      setForm({ current_password: '', new_password: '', confirm_password: '' });
    }, 'Пароль изменён. Сеансы на других устройствах завершены.');
  };
  return <>
    <div className="studio-section-heading"><div><span className="studio-eyebrow">АККАУНТ / БЕЗОПАСНОСТЬ</span><h2>Смена пароля</h2></div></div>
    <section className="studio-panel studio-narrow"><p className="studio-muted">Вы вошли как {user.email}. После смены пароля другие устройства должны будут войти заново.</p>
      <Notice {...action} />
      <form className="studio-form" onSubmit={save}>
        <label>Текущий пароль<input type="password" autoComplete="current-password" required value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} /></label>
        <label>Новый пароль<input type="password" autoComplete="new-password" minLength={12} required value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} /></label>
        <label>Повторите новый пароль<input type="password" autoComplete="new-password" minLength={12} required value={form.confirm_password} onChange={(e) => setForm({ ...form, confirm_password: e.target.value })} /></label>
        <p className="studio-muted">Не меньше 12 символов.</p>
        <button className="studio-primary" type="submit" disabled={action.busy}>Сменить пароль</button>
      </form>
    </section>
  </>;
}

export default function Admin() {
  const { site } = useSite();
  const [user, setUser] = useState(null);
  const [checked, setChecked] = useState(false);
  const [tab, setTab] = useState('overview');
  const [month, setMonth] = useState(monthNow());
  const action = useAction();
  useEffect(() => { api('/admin/session').then(setUser).catch(() => {}).finally(() => setChecked(true)); }, []);
  const logout = () => action.run(async () => { await api('/admin/logout', { method: 'POST' }); setUser(null); });
  if (!checked) return <div className="studio-loading">Открываем студию…</div>;
  if (!user) return <div className="studio-login"><div className="studio-login-art"><span>{site.site_name} / STUDIO</span>{site.logo_url && <img className="studio-login-logo" src={site.logo_url} alt={site.site_name} />}<h1>Здесь рождаются<br />новые истории.</h1><p>Контент, цифры и доходы — в одном пространстве.</p></div>
    <div className="studio-login-form"><AuthForm staff onAuthenticated={(account) => { setUser(account); setTab('overview'); }} /></div>
  </div>;
  const isOwner = user.role === 'superadmin';
  const tabs = [
    ['overview', '◫', 'Обзор'], ['catalog', '▤', 'Сериалы'], ['videos', '▷', 'Видео'],
    ...(isOwner ? [['finance', '◈', 'Финансы'], ['payments', '◉', 'Оплаты'], ['plans', '◇', 'Тарифы'], ['users', '♙', 'Пользователи'], ['categories', '▦', 'Жанры'], ['appearance', '◐', 'Оформление']] : []),
    ['security', '⚙', 'Безопасность'],
  ];
  const tabTitle = tabs.find((item) => item[0] === tab)?.[2] || 'Обзор';
  return <div className="studio">
    <aside className="studio-side"><Brand className="studio-brand-new" /><div className="studio-side-label">РАБОЧЕЕ ПРОСТРАНСТВО</div><nav aria-label="Разделы студии">{tabs.map(([id, icon, label]) => <button title={label} aria-label={label} className={tab === id ? 'active' : ''} key={id} onClick={() => setTab(id)}><b aria-hidden="true">{icon}</b>{label}</button>)}</nav><div className="studio-side-bottom"><div className="studio-profile"><span className="studio-avatar">{user.full_name.slice(0, 1).toUpperCase()}</span><span><strong>{user.full_name}</strong><small>{isOwner ? 'Супер-администратор' : user.role === 'moderator' ? 'Модератор' : 'Автор'}</small></span></div></div></aside>
    <main className="studio-main"><div className="studio-topline"><div><span>КАБИНЕТ / {tabTitle.toUpperCase()}</span><h1>{isOwner ? 'Панель владельца' : user.role === 'moderator' ? 'Кабинет модератора' : 'Кабинет автора'}</h1></div><div className="studio-top-actions"><label>Месяц <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></label><Link href="/" className="studio-secondary">На сайт ↗</Link><button type="button" className="studio-secondary studio-logout" onClick={logout} disabled={action.busy}>Выйти ↗</button></div></div>
      <Notice {...action} />
      {tab === 'overview' && <Dashboard user={user} month={month} />}
      {tab === 'catalog' && <Catalog user={user} />}
      {tab === 'videos' && <VideoLibrary onCatalog={() => setTab('catalog')} />}
      {tab === 'finance' && isOwner && <Finance month={month} />}
      {tab === 'payments' && isOwner && <Payments />}
      {tab === 'plans' && isOwner && <Plans />}
      {tab === 'users' && isOwner && <TeamPanel currentUser={user} />}
      {tab === 'categories' && isOwner && <Categories />}
      {tab === 'security' && <Security user={user} />}
      {tab === 'appearance' && isOwner && <AppearancePanel />}
    </main>
  </div>;
}
