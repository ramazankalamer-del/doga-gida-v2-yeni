import {useState,type FormEvent} from 'react';
import type {VisitRequest} from './CustomerVisits';

export default function RecoverAccount({request,token}:{request:VisitRequest;token:string}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function save(e:FormEvent<HTMLFormElement>){
  e.preventDefault();const form=e.currentTarget,values=new FormData(form);setError('');
  if(values.get('new_password')!==values.get('repeat_password')){setError('Yeni parolalar aynı olmalıdır.');return;}
  setBusy(true);
  try{await request('auth/recover',{token,username:values.get('username'),new_password:values.get('new_password')});form.reset();window.history.replaceState(null,'',window.location.pathname+'#hesabim');window.dispatchEvent(new Event('credentials-changed'));}
  catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <main className="login-page"><section className="modal"><span className="eyebrow">DOĞA GIDA</span><h1>Yönetici hesabını kurtar</h1><p>Bu bilgisayarda hazırlanan bağlantı 15 dakika geçerlidir ve bir kez kullanılabilir. Mevcut parolanı bilmen gerekmez. Kayıtların ve yönetici yetkin korunur.</p><form onSubmit={save}><fieldset disabled={busy}><label>Yeni yönetici kullanıcı adı<input name="username" autoComplete="username" required minLength={1} maxLength={100} autoCapitalize="none" spellCheck={false}/></label><label>Yeni yönetici parolası<input name="new_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128}/></label><label>Yeni yönetici parolası tekrar<input name="repeat_password" type="password" autoComplete="new-password" required minLength={12} maxLength={128}/></label><p className="order-help">En az 12 karakterli bir parola belirle. Parolanı sohbete yazma. Kaydettikten sonra yeni bilgilerinle giriş yap.</p>{error&&<p className="error" role="alert">{error}</p>}<button className="primary">{busy?'Kaydediliyor…':'Yeni giriş bilgilerimi kaydet'}</button></fieldset></form></section></main>;
}
