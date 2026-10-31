'use client';

import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useSite } from './SiteProvider';

function useTask() {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const run = async (task, success = '') => {
    setBusy(true); setError(''); setMessage('');
    try { await task(); setMessage(success); } catch (caught) { setError(caught.message); } finally { setBusy(false); }
  };
  return { busy, error, message, run };
}
function Feedback({ error, message }) {
  return <>{error && <p className="studio-notice error" role="alert">{error}</p>}{message && <p className="studio-notice success" role="status">{message}</p>}</>;
}

export function AppearancePanel() {
  const { site, refresh } = useSite();
  const [form, setForm] = useState(site);
  const task = useTask();
  useEffect(() => setForm(site), [site]);
  const update = (name, value) => setForm((current) => ({ ...current, [name]: value }));
  const upload = (name, file) => {
    if (!file) return;
    task.run(async () => {
      const body = new FormData(); body.append('file', file);
      const result = await api('/admin/covers', { method: 'POST', body }); update(name, result.url);
    }, 'Изображение загружено. Сохраните оформление, чтобы опубликовать его.');
  };
  const save = (event) => {
    event.preventDefault(); task.run(async () => {
      await api('/admin/appearance', { method: 'PUT', body: JSON.stringify(form) }); await refresh();
    }, 'Оформление опубликовано на сайте');
  };
  const themes = [['midnight', 'Полночь', 'Тёмно-синий и золотой'], ['winter', 'Зимняя премьера', 'Холодный свет и снежные блики'], ['aurora', 'Северное сияние', 'Мягкие зелёные и фиолетовые оттенки']];
  return <><div className="studio-section-heading"><div><span className="studio-eyebrow">БРЕНД И СЕЗОНЫ</span><h2>Оформление сайта</h2></div><a href="/" target="_blank" rel="noreferrer" className="studio-secondary">Открыть главную ↗</a></div><Feedback {...task} />
    <form className="studio-form" onSubmit={save}><div className="studio-two"><section className="studio-panel"><h3>Первое впечатление</h3>
      <label>Название платформы<input required maxLength={40} value={form.site_name} onChange={(e) => update('site_name', e.target.value)} /></label>
      <label>Надпись над заголовком<input maxLength={90} value={form.hero_kicker} onChange={(e) => update('hero_kicker', e.target.value)} /></label>
      <label>Главный заголовок<input required maxLength={140} value={form.hero_title} onChange={(e) => update('hero_title', e.target.value)} /></label>
      <label>Описание<textarea maxLength={400} rows={3} value={form.hero_subtitle} onChange={(e) => update('hero_subtitle', e.target.value)} /></label>
      <label>Цвет акцентов<input type="color" value={form.accent_color} onChange={(e) => update('accent_color', e.target.value)} /></label>
    </section><section className="studio-panel"><h3>Изображения</h3><div className="appearance-logo-preview">{form.logo_url && <img src={form.logo_url} alt="Предпросмотр логотипа" />}<div><label className="studio-upload">Загрузить логотип<input disabled={task.busy} type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => upload('logo_url', e.target.files?.[0])} /></label><p className="studio-muted">Квадратное изображение, до 3 МБ.</p><button className="studio-text-button" type="button" onClick={() => update('logo_url', '/brand/aikadr-square.png')}>Исходный логотип</button></div></div>
      <label className="studio-upload">Загрузить фон главной<input disabled={task.busy} type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => upload('hero_background_url', e.target.files?.[0])} /></label>
      <p className="studio-muted">Для фона лучше широкое изображение от 1920 × 1080, до 3 МБ.</p>
      {form.hero_background_url && <><img className="appearance-background-preview" src={form.hero_background_url} alt="Предпросмотр фона" /><button className="studio-text-button danger" type="button" onClick={() => update('hero_background_url', '')}>Убрать изображение фона</button></>}
    </section></div><section className="studio-panel"><h3>Сезонная тема</h3><div className="appearance-themes">{themes.map(([id, title, description]) => <button key={id} className={`appearance-theme ${id} ${form.theme === id ? 'selected' : ''}`} type="button" aria-pressed={form.theme === id} onClick={() => update('theme', id)}><strong>{title}</strong><small>{description}</small>{form.theme === id && <span>Выбрана ✓</span>}</button>)}</div></section><div className="studio-actions"><button type="submit" className="studio-primary" disabled={task.busy}>Сохранить оформление</button></div></form>
  </>;
}

export function VideoLibrary({ onCatalog }) {
  const [videos, setVideos] = useState([]), [loading, setLoading] = useState(true);
  const task = useTask();
  const load = () => api('/admin/videos').then(setVideos);
  useEffect(() => { task.run(load).finally(() => setLoading(false)); }, []);
  const remove = (video) => {
    if (!confirm(`Удалить файл «${video.original_name}»? Серия останется в каталоге, файл будет удалён безвозвратно.`)) return;
    task.run(async () => { await api(`/admin/videos/${video.id}`, { method: 'DELETE' }); await load(); }, 'Видео удалено, серия сохранена');
  };
  const total = videos.reduce((sum, item) => sum + item.byte_size, 0);
  return <><div className="studio-section-heading"><div><span className="studio-eyebrow">МЕДИАТЕКА / {videos.length} ФАЙЛОВ</span><h2>Видео</h2></div><button className="studio-primary" onClick={onCatalog}>Загрузить в сериал ↗</button></div><Feedback {...task} />
    <div className="studio-kpis"><article className="studio-kpi"><span>Занято видеофайлами</span><strong>{(total / 1024 ** 3).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ГБ</strong><small>Без учёта служебных данных и резервных копий</small></article></div>
    <section className="studio-panel studio-table-panel"><div className="studio-table-wrap"><table className="studio-table"><thead><tr><th>Файл / серия</th><th>Автор</th><th>Размер</th><th>Загружен</th><th>Действия</th></tr></thead><tbody>{videos.map((video) => <tr key={video.id}><td><strong>{video.original_name}</strong><small>{video.series_title} · С{video.season}, Э{video.number} — {video.episode_title}</small></td><td>{video.author_name || 'Редакция'}</td><td>{(video.byte_size / 1024 ** 2).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} МБ</td><td>{new Date(video.created_at * 1000).toLocaleDateString('ru-RU')}</td><td><div className="studio-actions"><a className="studio-text-button" href={`/api/videos/${video.episode_id}`} target="_blank" rel="noreferrer">Посмотреть ↗</a><button className="studio-text-button danger" disabled={task.busy} onClick={() => remove(video)}>Удалить файл</button></div></td></tr>)}{!videos.length && <tr><td colSpan={5}>{loading ? 'Загружаем…' : 'Загруженных видео пока нет. Создайте эпизод в разделе «Сериалы» и выберите файл.'}</td></tr>}</tbody></table></div></section>
  </>;
}

const blankUser = { full_name: '', email: '', password: '', role: 'author', is_active: true, storage_quota_gb: 10 };
const roles = { viewer: 'Зритель', author: 'Автор', moderator: 'Модератор', superadmin: 'Супер-администратор' };
export function TeamPanel({ currentUser }) {
  const [users, setUsers] = useState([]), [selected, setSelected] = useState(null), [form, setForm] = useState(blankUser);
  const task = useTask();
  const load = () => api('/admin/users').then(setUsers);
  useEffect(() => { task.run(load); }, []);
  const choose = (user) => { setSelected(user?.id || null); setForm(user ? { ...user, password: '', storage_quota_gb: Math.round(user.storage_quota_bytes / 1024 ** 3) } : blankUser); };
  const save = (event) => {
    event.preventDefault(); task.run(async () => {
      const body = selected ? { full_name: form.full_name, role: form.role, is_active: form.is_active, storage_quota_gb: Number(form.storage_quota_gb) } : { ...form, storage_quota_gb: Number(form.storage_quota_gb) };
      await api(selected ? `/admin/users/${selected}` : '/admin/users', { method: selected ? 'PUT' : 'POST', body: JSON.stringify(body) });
      await load(); choose(null);
    }, selected ? 'Аккаунт обновлён' : 'Аккаунт создан. Передайте временный пароль владельцу аккаунта; при входе потребуется код из письма.');
  };
  return <><div className="studio-section-heading"><div><span className="studio-eyebrow">КОМАНДА И ДОСТУПЫ</span><h2>Пользователи</h2></div><button className="studio-primary" onClick={() => choose(null)}>Новый аккаунт</button></div><Feedback {...task} /><div className="studio-two"><section className="studio-panel"><h3>{selected ? 'Изменить аккаунт' : 'Добавить пользователя'}</h3><form className="studio-form" onSubmit={save}>
    <label>Имя<input required minLength={2} maxLength={120} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label><label>Email<input required type="email" disabled={!!selected} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
    {!selected && <label>Временный пароль<input type="password" required minLength={12} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>}
    <label>Роль<select disabled={selected === currentUser.id} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{Object.entries(roles).map(([id,title]) => <option value={id} key={id}>{title}</option>)}</select></label>
    {form.role === 'author' && <label>Место для всех сериалов автора, ГБ<input type="number" min="1" max="1000" step="1" required value={form.storage_quota_gb} onChange={(e) => setForm({ ...form, storage_quota_gb: e.target.value })} />{selected && <small>Занято: {(users.find((item) => item.id === selected)?.storage_used_bytes / 1024 ** 3 || 0).toFixed(2)} ГБ из {form.storage_quota_gb} ГБ</small>}</label>}
    {selected && <div className="studio-checks"><label><input type="checkbox" disabled={selected === currentUser.id} checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Доступ разрешён</label></div>}
    <p className="studio-muted">Супер-администратор управляет всей платформой. Модератор — каталогом и видео. Автор — своими материалами и показателями.</p><button type="submit" className="studio-primary" disabled={task.busy}>{selected ? 'Сохранить' : 'Создать аккаунт'}</button>
  </form></section><section className="studio-panel"><h3>Аккаунты ({users.length})</h3><div className="studio-team-list">{users.map((user) => <button key={user.id} className={selected === user.id ? 'selected' : ''} onClick={() => choose(user)}><span className="studio-avatar">{user.full_name.slice(0,1)}</span><span><strong>{user.full_name}</strong><small>{user.email}</small><small>{roles[user.role]} · {user.is_active ? 'Активен' : 'Отключён'} · {user.email_verified ? 'Почта подтверждена' : user.role === 'viewer' ? 'Ожидает подтверждения' : 'Почта не подтверждена'}</small>{user.role === 'author' && <small>Видео: {(user.storage_used_bytes / 1024 ** 3).toFixed(2)} / {(user.storage_quota_bytes / 1024 ** 3).toFixed(0)} ГБ</small>}</span><b aria-hidden="true">↗</b></button>)}</div></section></div></>;
}
