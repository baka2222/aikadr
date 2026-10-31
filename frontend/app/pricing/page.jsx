'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

export default function Pricing() {
  const [plans, setPlans] = useState([]);
  const [instructions, setInstructions] = useState('');
  const [paymentReady, setPaymentReady] = useState(false);
  const [methods, setMethods] = useState([]);
  const [methodId, setMethodId] = useState('');
  const [user, setUser] = useState(null);
  const [selected, setSelected] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    Promise.all([api('/plans'), api('/payment-instructions')]).then(([items, info]) => { setPlans(items); setInstructions(info.text); setPaymentReady(info.ready); setMethods(info.methods || []); setMethodId(info.methods?.[0]?.id || ''); if (items.length) setSelected(items[0].id); }).catch((caught) => setError(caught.message)).finally(() => setLoading(false));
    api('/auth/me').then(setUser).catch(() => {});
  }, []);
  const submit = async (event) => {
    event.preventDefault();
    if (!receipt) { setError('Приложите скриншот чека'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const body = new FormData(); body.append('plan_id', selected); body.append('payment_method_id', methodId); body.append('receipt', receipt);
      await api('/payments', { method: 'POST', body });
      setMessage('Чек отправлен. Администратор проверит поступление денег и активирует подписку.');
      setReceipt(null); event.target.reset();
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  };
  const current = plans.find((item) => item.id === selected);
  return <div className="member-page"><section className="member-hero"><div className="kicker">КАДР / ПОДПИСКА</div><h1>Смотрите без паузы.</h1><p>Выберите срок доступа ко всем сериалам платформы.</p></section>
    <div className="member-content"><div className="member-plans">{plans.map((item) => <button key={item.id} type="button" className={`member-plan ${selected === item.id ? 'selected' : ''}`} onClick={() => setSelected(item.id)}><span className="member-label">{item.duration_days} ДНЕЙ ДОСТУПА</span><h2>{item.title}</h2><p>{item.description}</p><strong>{new Intl.NumberFormat('ru-RU').format(item.price_som)} <small>сом</small></strong><span className="member-plan-select">{selected === item.id ? 'Выбран ✓' : 'Выбрать →'}</span></button>)}</div>
      {error && <p className="member-error" role="alert">{error}</p>}
      {loading ? <p role="status">Загружаем тарифы…</p> : !plans.length && !error && <div className="empty"><h2>Подписки скоро появятся</h2><p>Мы готовим тарифы. Пока можно познакомиться с каталогом.</p><Link className="button" href="/catalog">Открыть каталог →</Link></div>}
      <div className="member-grid member-checkout"><section className="member-card"><span className="member-label">КАК ОПЛАТИТЬ</span><h2>Перевод и чек.</h2><p className="member-instructions">{instructions || 'Реквизиты скоро появятся.'}</p>{methods.length > 0 && <div className="member-payment-methods">{methods.map((item) => <button type="button" key={item.id} className={methodId === item.id ? 'selected' : ''} onClick={() => setMethodId(item.id)}><strong>{item.title}</strong><span>{item.details}</span></button>)}</div>}<p className="member-fine">После перевода приложите скриншот чека. Подписка включится только после ручной проверки поступления денег. Данные вашей карты сайт не запрашивает.</p></section>
        <section className="member-card"><span className="member-label">ШАГ 02 / ПРОВЕРКА</span><h2>Подтвердить оплату</h2>{!paymentReady || !plans.length ? <div className="member-checkout-blocked"><p><strong>Здесь появится поле «Скриншот чека».</strong></p><p>{!plans.length ? 'Сначала администратор должен создать активный тариф.' : !methods.length ? 'Сейчас добавлена только общая инструкция. Администратору нужно создать активный способ оплаты в разделе «Тарифы → Способы оплаты».' : 'Администратору нужно сохранить общую инструкцию по оплате.'}</p>{user?.role === 'superadmin' && <Link className="button" href="/admin">Перейти в панель →</Link>}</div> : user?.role === 'viewer' ? <form onSubmit={submit}><p>{current ? `${current.title} · ${new Intl.NumberFormat('ru-RU').format(current.price_som)} сом` : 'Выберите тариф выше.'}</p><label>Способ оплаты<select value={methodId} onChange={(e) => setMethodId(e.target.value)} required>{methods.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label><label>Скриншот чека<input required type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setReceipt(e.target.files?.[0])} /></label>{message && <p className="member-success">{message}</p>}<button className="button" type="submit" disabled={busy || !selected || !methodId}>{busy ? 'Отправляем…' : 'Отправить чек →'}</button></form> : <><p>Для отправки чека войдите в аккаунт зрителя. Аккаунт администратора не покупает подписку.</p><Link className="button" href="/account">Войти или зарегистрироваться →</Link></>}</section></div>
    </div></div>;
}
