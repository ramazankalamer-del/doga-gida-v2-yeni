import { useEffect, useState, type FormEvent } from 'react';

type Role = 'admin'|'staff'|'viewer';
type Account = {id:number;username:string;role:Role;active:number};
type Request = <T>(path:string,data?:object)=>Promise<T>;
const roles:Record<Role,string> = {admin:'Yönetici',staff:'Personel',viewer:'Salt okunur'};

function AccountRow({account,self,busy,onSave}:{account:Account;self:boolean;busy:boolean;onSave:(id:number,role:Role,active:boolean)=>Promise<void>}){
 const [role,setRole]=useState(account.role),[active,setActive]=useState(Boolean(account.active));
 useEffect(()=>{setRole(account.role);setActive(Boolean(account.active));},[account]);
 return <tr><td><strong>{account.username}</strong>{self&&<small>Bu hesap sizsiniz</small>}</td><td><select aria-label={`${account.username} rolü`} disabled={self||busy} value={role} onChange={e=>setRole(e.target.value as Role)}>{Object.entries(roles).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></td><td><label className="account-active"><input type="checkbox" aria-label={`${account.username} aktif`} checked={active} disabled={self||busy} onChange={e=>setActive(e.target.checked)}/>{active?'Aktif':'Pasif'}</label></td><td><button className="secondary" disabled={self||busy||(role===account.role&&active===Boolean(account.active))} onClick={()=>void onSave(account.id,role,active)}>Kaydet</button></td></tr>;
}

export default function UserManagement({request,currentUserId}:{request:Request;currentUserId:number}){
 const [accounts,setAccounts]=useState<Account[]>([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function load(){setLoading(true);setError('');try{setAccounts(await request<Account[]>('users'));}catch(e){setError((e as Error).message);}finally{setLoading(false);}}
 useEffect(()=>{void load();},[]);
 async function create(e:FormEvent<HTMLFormElement>){e.preventDefault();const form=e.currentTarget;const data=Object.fromEntries(new FormData(form));setBusy(true);setError('');setNotice('');try{const account=await request<Account>('users',data);setAccounts(old=>[...old,account]);form.reset();setNotice('Kullanıcı oluşturuldu.');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function save(id:number,role:Role,active:boolean){setBusy(true);setError('');setNotice('');try{const account=await request<Account>(`users/${id}`,{role,active});setAccounts(old=>old.map(a=>a.id===id?account:a));setNotice('Kullanıcı güncellendi. Değişen hesabın açık oturumları kapatıldı.');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <><div className="page-heading"><div><span className="eyebrow">YÖNETİCİ ALANI</span><h1>Kullanıcılar<span>.</span></h1><p>Çalışma alanına erişimi ve kullanıcı rollerini yönetin.</p></div></div>
 {error&&<div className="error" role="alert">{error}</div>}{notice&&<div className="notice" role="status">{notice}</div>}
 <section className="panel"><div className="panel-head"><div><h2>Kullanıcı listesi</h2><p>Rol veya aktiflik değiştiğinde kullanıcı yeniden giriş yapmalıdır.</p></div><button className="secondary" disabled={busy||loading} onClick={()=>void load()}>Yenile</button></div>{loading?<p className="loading" role="status">Kullanıcılar yükleniyor…</p>:<div className="table-wrap"><table><thead><tr><th>KULLANICI ADI</th><th>ROL</th><th>DURUM</th><th>İŞLEM</th></tr></thead><tbody>{accounts.map(a=><AccountRow key={a.id} account={a} self={a.id===currentUserId} busy={busy} onSave={save}/>)}</tbody></table></div>}</section>
 <section className="panel user-create"><div className="panel-head"><div><h2>Kullanıcı oluştur</h2><p>En az 12 karakterli bir parola belirleyin. İlk yöneticiyi yerel kurulum komutuyla oluşturabilirsiniz.</p></div></div><form onSubmit={create}><label>Kullanıcı adı<input name="username" autoComplete="off" required maxLength={100}/></label><label>İlk parola<input name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={128}/></label><label>Yeni kullanıcı rolü<select name="role" defaultValue="viewer">{Object.entries(roles).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><button className="primary" disabled={busy||loading}>{busy?'Kaydediliyor…':'Kullanıcı oluştur'}</button></form></section></>;
}
