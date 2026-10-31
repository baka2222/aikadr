'use client';

import { useEffect, useState } from 'react';
import { api } from '../lib/api';

export default function AuthForm({ staff = false, onAuthenticated }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ full_name: '', email: '', password: '' });
  const [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!remaining) return;
    const timer = setTimeout(() => setRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => clearTimeout(timer);
  }, [remaining]);
  const begin = async (event) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const path = mode === 'register' ? '/auth/register' : mode === 'reset' ? '/auth/reset-password' : staff ? '/admin/login' : '/auth/login';
      const body = mode === 'register' ? form : mode === 'reset' ? { email: form.email } : { email: form.email, password: form.password };
      const result = await api(path, { method: 'POST', body: JSON.stringify(body) });
      setForm((value) => ({ ...value, password: '' }));
      if (staff && mode === 'login') {
        await onAuthenticated(result);
      } else {
        setChallenge(result); setRemaining(result.resend_after);
      }
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  };
  const verify = async (event) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      if (mode === 'reset' && newPassword !== confirmation) throw new Error('Пароли не совпадают');
      const account = await api('/auth/verify-email', { method: 'POST', body: JSON.stringify({
        challenge_id: challenge.challenge_id, code, ...(mode === 'reset' ? { new_password: newPassword } : {}),
      }) });
      if (staff && account.role === 'viewer') {
        await api('/auth/logout', { method: 'POST' });
        throw new Error('Студия доступна авторам и администрации');
      }
      await onAuthenticated(account);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  };
  const resend = async () => {
    setBusy(true); setError('');
    try {
      const next = await api('/auth/resend-code', { method: 'POST', body: JSON.stringify({ challenge_id: challenge.challenge_id }) });
      setChallenge(next); setRemaining(next.resend_after); setCode('');
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  };
  const changeMode = (next) => { setMode(next); setError(''); setChallenge(null); setCode(''); setNewPassword(''); setConfirmation(''); };
  return <div className="auth-flow">
    <span className="member-label">{challenge ? 'ПОДТВЕРЖДЕНИЕ ПОЧТЫ' : staff ? 'AIKADR / STUDIO' : 'ВАША СЛЕДУЮЩАЯ ИСТОРИЯ'}</span>
    <h2>{challenge ? 'Проверьте почту' : mode === 'register' ? 'Добро пожаловать' : mode === 'reset' ? 'Восстановить доступ' : 'С возвращением'}</h2>
    <p className="auth-description">{challenge ? `${mode === 'reset' ? 'Если аккаунт существует, код отправлен на' : 'Код отправлен на'} ${challenge.email}. Введите 6 цифр из письма.` : mode === 'reset' ? 'Отправим код для создания нового пароля.' : staff ? 'Войдите в студию по email и паролю.' : 'Подтвердите вход кодом из письма — это защищает ваш аккаунт.'}</p>
    {challenge ? <form onSubmit={verify} className="auth-form">
      <label>Код из письма<input className="auth-code" required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" /></label>
      {mode === 'reset' && <><label>Новый пароль<input type="password" minLength={12} maxLength={256} autoComplete="new-password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label><label>Повторите пароль<input type="password" minLength={12} autoComplete="new-password" required value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></label></>}
      {error && <p className="member-error" role="alert">{error}</p>}
      <button className="button" disabled={busy || code.length !== 6} type="submit">{busy ? 'Проверяем…' : 'Подтвердить и войти'}<span aria-hidden="true">↗</span></button>
      <p className="auth-hint">Код действует 10 минут. Проверьте папку «Спам», если письма нет во входящих.</p>
      <button className="member-link" type="button" disabled={busy || remaining > 0} onClick={resend}>{remaining > 0 ? `Отправить повторно через ${remaining} с` : 'Отправить новый код'}</button>
      <button className="member-link" type="button" disabled={busy} onClick={() => changeMode(mode)}>← Изменить email или начать заново</button>
    </form> : <form onSubmit={begin} className="auth-form">
      {mode === 'register' && <label>Ваше имя<input required minLength={2} maxLength={120} autoComplete="name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>}
      <label>Email<input required type="email" maxLength={254} autoComplete="username" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
      {mode !== 'reset' && <label>Пароль<input required type="password" minLength={mode === 'register' ? 12 : undefined} maxLength={256} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>}
      {mode === 'register' && <p className="auth-hint">Придумайте пароль длиной от 12 символов.</p>}
      {error && <p className="member-error" role="alert">{error}</p>}
      <button className="button" type="submit" disabled={busy}>{busy ? staff && mode === 'login' ? 'Входим…' : 'Отправляем код…' : staff && mode === 'login' ? 'Войти в студию' : 'Получить код'}<span aria-hidden="true">↗</span></button>
      {mode === 'login' && <button type="button" className="member-link" disabled={busy} onClick={() => changeMode('reset')}>Не помню пароль</button>}
      {!staff && mode !== 'reset' && <button type="button" className="member-link" disabled={busy} onClick={() => changeMode(mode === 'login' ? 'register' : 'login')}>{mode === 'login' ? 'Впервые здесь? Создать аккаунт' : 'Уже есть аккаунт? Войти'}</button>}
      {mode === 'reset' && <button type="button" className="member-link" disabled={busy} onClick={() => changeMode('login')}>← Вернуться ко входу</button>}
    </form>}
  </div>;
}
