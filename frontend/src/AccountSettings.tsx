import {useState,type FormEvent} from 'react';
import type {VisitRequest} from './CustomerVisits';

export default function AccountSettings({request,username}:{request:VisitRequest;username:string}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function save(e:FormEvent<HTMLFormElement>){
  e.preventDefault();const form=e.currentTarget,values=new FormData(form);setError('');
  if(values.get('new_password')!==values.get('repeat_password')){setError('Yeni parolalar aynı olmalıdır.');return;}
  setBusy(true);
  try{
   await request('auth/credentials',{username:values.get('username'),current_password:values.get('current_password'),new_password:values.get('new_password')});
   form.reset();window.dispatchEvent(new Event('credentials-changed'));
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <><div className="page-heading"><div><span className="eyebrow">HESAP AYARLARI</span><h1>Hesabım<span>.</span></h1><p>Kullanıcı adınızı ve parolanızı değiştirin.</p></div></div><section className="panel finance-section"><h2>Giriş bilgileri</h2><p className="order-help">Şu anki kullanıcı adınız: <strong>{username}</strong>. Kaydettiğinizde bu hesabın tüm açık oturumları kapanır. Yeni bilgilerinizle tekrar giriş yapmanız gerekir.</p><form className="finance-form" onSubmit={save}><fieldset disabled={busy}><label>Yeni kullanıcı adı<input name="username" autoComplete="username" defaultValue={username} required minLength={1} maxLength={100} autoCapitalize="none" spellCheck={false}/></label><label>Mevcut parola<input name="current_password" type="password" autoComplete="current-password" required maxLength={128}/></label><label>Yeni parola<input name="new_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128}/></label><label>Yeni parola tekrar<input name="repeat_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128}/></label><p className="order-help">En az 12 karakter kullanın. Parolanızı sohbet üzerinden paylaşmayın.</p>{error&&<p className="error" role="alert">{error}</p>}<button className="primary">{busy?'Kaydediliyor…':'Giriş bilgilerini değiştir'}</button></fieldset></form></section></>;
}
