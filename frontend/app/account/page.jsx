'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import AuthForm from '../../components/AuthForm';
import { api } from '../../lib/api';
import { useSite } from '../../components/SiteProvider';

const date = (stamp) => new Date(stamp * 1000).toLocaleDateString('ru-RU');
export default function Account() {
  const { site } = useSite();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [payments, setPayments] = useState([]);
  const [error, setError] = useState('');
  const load = async () => {
    const account = await api('/auth/me'); setUser(account);
    setPayments(await api('/payments/mine'));
  };
  useEffect(() => { load().catch(() => {}).finally(() => setLoading(false)); }, []);
  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }); setUser(null); setPayments([]); }
    catch (caught) { setError(caught.message); }
  };
  return <div className="member-page"><section className="member-hero"><div className="kicker">{site.site_name} / ПРОФИЛЬ</div><h1>{user ? `Привет, ${user.full_name}.` : 'Ваш вход в истории.'}</h1><p>{user ? 'Подписка и заявки на оплату в одном месте.' : 'Один аккаунт — целый мир авторского кино.'}</p></section>
    <div className="member-content">{error && <p role="alert" className="member-error">{error}</p>}{loading ? <div className="member-card">Открываем аккаунт…</div> : user ? <>
      <div className="member-grid"><section className="member-card"><span className="member-label">ПОДПИСКА</span><h2>{user.subscription ? 'Доступ открыт' : 'Выберите свою историю'}</h2><p>{user.subscription ? `Активна до ${date(user.subscription.ends_at)} · ${user.subscription.plan_title}` : 'Управляйте подпиской и доступом к сериалам.'}</p><Link className="button" href="/pricing">{user.subscription ? 'Продлить подписку ↗' : 'Посмотреть тарифы ↗'}</Link></section>
        <section className="member-card"><span className="member-label">АККАУНТ</span><h2>{user.full_name}</h2><p>{user.email}</p><p className="account-verified">{user.email_verified ? '✓ Почта подтверждена' : 'Почта пока не подтверждена'}</p>{user.role !== 'viewer' && <Link className="button outline" href="/admin">В рабочий кабинет ↗</Link>}<button className="member-link" onClick={logout}>Выйти из аккаунта ↗</button></section></div>
      <section className="member-card"><span className="member-label">ИСТОРИЯ ОПЛАТ</span><h2>Мои заявки</h2>{payments.length ? payments.map((item) => <div className="member-row" key={item.id}><strong>{item.plan_title}</strong><span>{new Intl.NumberFormat('ru-RU').format(item.price_som)} сом</span><em className={item.status}>{item.status === 'pending' ? 'На проверке' : item.status === 'approved' ? 'Подтверждено' : 'Отклонено'}</em></div>) : <p>Заявок пока нет.</p>}</section>
    </> : <div className="member-grid"><section className="member-card member-auth"><AuthForm onAuthenticated={load} /></section><section className="member-card member-story"><span className="member-label">{site.site_name} / ВАШ ЛИЧНЫЙ ЭКРАН</span><h2>У хорошей истории<br />нет границ.</h2><p>Открывайте авторские миры, выбирайте новые сериалы и возвращайтесь к тому, что хочется досмотреть.</p>{site.logo_url && <img className="account-brand-image" src={site.logo_url} alt={site.site_name} />}</section></div>}</div>
  </div>;
}
