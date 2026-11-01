import { useEffect, useState, type FormEvent } from 'react';

type Balance = {id:number;name:string;sales_cents:number;collected_cents:number;balance_cents:number};
type Collection = {id:number;customer_id:number|null;customer:string|null;amount_cents:number;date:string;method:'cash'|'transfer'|'card'|null;note:string;can_cancel:boolean;cancellation:{reason:string;cancelled_at:string}|null};
type Request = <T>(path:string,data?:object)=>Promise<T>;
const methods = {cash:'Nakit',transfer:'Havale / EFT',card:'Kart'};
const money = (cents:number)=>new Intl.NumberFormat('tr-TR',{style:'currency',currency:'TRY'}).format(cents/100);

export default function Collections({request,canWrite,canCancel,onSaved,customerFilter='',onFilter}:{customerFilter?:string;onFilter:(id:string)=>void;request:Request;canWrite:boolean;canCancel:boolean;onSaved:()=>Promise<void>}){
 const [balances,setBalances]=useState<Balance[]>([]),[collections,setCollections]=useState<Collection[]>([]);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[opened,setOpened]=useState(false);
 const [cancelTarget,setCancelTarget]=useState<Collection|null>(null),[cancelReason,setCancelReason]=useState('');
 const [filter,setFilter]=useState(customerFilter),[requestId,setRequestId]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function load(){setLoading(true);setError('');try{const [b,c]=await Promise.all([request<Balance[]>('customer-balances'),request<Collection[]>('collections')]);setBalances(b);setCollections(c);}catch(e){setError((e as Error).message);}finally{setLoading(false);}}
 useEffect(()=>{void load();},[]);
 useEffect(()=>{if(!opened)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!busy)setOpened(false);};document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close);},[opened,busy]);
 useEffect(()=>{if(!cancelTarget)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!busy)setCancelTarget(null);};document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close);},[cancelTarget,busy]);
 function open(){setRequestId(crypto.randomUUID());setError('');setNotice('');setOpened(true);}
 async function submit(e:FormEvent<HTMLFormElement>){
  e.preventDefault();setBusy(true);setError('');
  const data=Object.fromEntries(new FormData(e.currentTarget));
  try{await request<Collection>('collections',{...data,customer_id:Number(data.customer_id),request_id:requestId});setOpened(false);await load();setNotice('Tahsilat kaydedildi. Müşteri bakiyesi güncellendi.');await onSaved();}
  catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function cancel(e:FormEvent){e.preventDefault();if(!cancelTarget)return;setBusy(true);setError('');setNotice('');try{await request<Collection>(`collections/${cancelTarget.id}/cancel`,{reason:cancelReason});setCancelTarget(null);await load();setNotice('Tahsilat iptal edildi. Müşteri bakiyesi ve tahsilat özeti güncellendi.');await onSaved();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const visibleBalances=balances.filter(b=>!filter||b.id===Number(filter));
 const visibleCollections=collections.filter(c=>!filter||c.customer_id===Number(filter));
 const unassigned=collections.filter(c=>c.customer_id===null&&!c.cancellation).reduce((sum,c)=>sum+c.amount_cents,0);
 return <>
  <div className="page-heading"><div><span className="eyebrow">MÜŞTERİ HESAPLARI</span><h1>Tahsilat ve bakiyeler<span>.</span></h1><p>Tahsilatları kaydedin, müşterilerinizin borç ve alacaklarını izleyin.</p></div>{canWrite&&<button className="primary" disabled={loading||busy} onClick={open}>Tahsilat ekle</button>}</div>
  {notice&&<div className="notice" role="status">{notice}</div>}
  {error&&!opened&&!cancelTarget&&<div className="error" role="alert">{error}<button onClick={()=>void load()}>Tekrar dene</button></div>}
  {loading?<p className="loading" role="status">Hesaplar yükleniyor…</p>:<>
   <div className="collection-filter"><label>Müşteriye göre filtrele<select aria-label="Müşteriye göre filtrele" value={filter} onChange={e=>{setFilter(e.target.value);onFilter(e.target.value);}}><option value="">Tüm müşteriler</option>{balances.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label><p>Bakiye = iptal edilmemiş siparişler − müşteriye bağlı geçerli tahsilatlar. Eksi bakiye müşterinin alacağıdır.</p></div>
   {unassigned>0&&<p className="collection-info">Müşterisi belirtilmeyen eski tahsilat toplamı: <strong>{money(unassigned)}</strong>. Bu kayıtlar kendi tarihlerindeki tahsilat toplamlarına dahildir; müşteri bakiyelerinden düşülmez.</p>}
   <section className="panel"><div className="panel-head"><h2>Müşteri bakiyeleri</h2></div><div className="table-wrap"><table><thead><tr><th>MÜŞTERİ</th><th>BAKİYE</th><th>SİPARİŞ TOPLAMI</th><th>TAHSİLAT TOPLAMI</th></tr></thead><tbody>{visibleBalances.map(b=><tr key={b.id}><td><strong>{b.name}</strong></td><td><strong>{money(b.balance_cents)}</strong><small>{b.balance_cents>0?'Müşterinin borcu':b.balance_cents<0?'Müşterinin alacağı':'Hesap kapalı'}</small></td><td>{money(b.sales_cents)}</td><td>{money(b.collected_cents)}</td></tr>)}</tbody></table>{!visibleBalances.length&&<p className="empty">Müşteri bulunmuyor.</p>}</div></section>
   <section className="panel collection-list"><div className="panel-head"><div><h2>Tahsilat listesi</h2><p>Bu ekran kayıt tutar; banka veya karttan ödeme çekmez.</p></div></div><div className="table-wrap"><table><thead><tr><th>KAYIT / MÜŞTERİ</th><th>TARİH</th><th>TUTAR</th><th>YÖNTEM</th><th>AÇIKLAMA</th></tr></thead><tbody>{visibleCollections.map(c=><tr key={c.id}><td><strong>{c.customer||'Müşterisi belirtilmemiş eski kayıt'}</strong><small>TH-{String(c.id).padStart(4,'0')}</small>{c.cancellation?<><span className="badge neutral">İptal edildi</span><small>İptal nedeni: {c.cancellation.reason}</small></>:canCancel&&c.can_cancel&&<button className="secondary row-edit" disabled={busy} aria-label={`TH-${String(c.id).padStart(4,'0')} iptal et`} onClick={()=>{setCancelTarget(c);setCancelReason('');setError('');setNotice('');}}>İptal et</button>}</td><td>{new Date(c.date+'T12:00:00').toLocaleDateString('tr-TR')}</td><td className={c.cancellation?'cancelled-amount':''}>{money(c.amount_cents)}</td><td>{c.method?methods[c.method]:'Belirtilmemiş'}</td><td>{c.note||'—'}</td></tr>)}</tbody></table>{!visibleCollections.length&&<p className="empty">Henüz tahsilat bulunmuyor.</p>}</div></section>
  </>}
  {cancelTarget&&<div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="collection-cancel-title"><div className="panel-head"><h2 id="collection-cancel-title">Tahsilatı iptal et</h2><button className="secondary" disabled={busy} onClick={()=>setCancelTarget(null)}>Kapat</button></div><form onSubmit={cancel}><p><strong>TH-{String(cancelTarget.id).padStart(4,'0')} · {cancelTarget.customer} · {money(cancelTarget.amount_cents)}</strong></p><p>Bu kayıt iptal edilecek. Müşteri bakiyesi ve tahsilat özeti yeniden hesaplanacak; kayıt ve açıklaması saklanacak. Banka veya kart üzerinden para iadesi yapılmaz.</p><label>Tahsilat iptal nedeni<input required minLength={3} maxLength={500} autoFocus value={cancelReason} disabled={busy} onChange={e=>setCancelReason(e.target.value)}/></label>{error&&<div className="error" role="alert">{error}</div>}<div className="form-actions"><button className="secondary" type="button" disabled={busy} onClick={()=>setCancelTarget(null)}>Vazgeç</button><button className="primary" disabled={busy}>{busy?'İptal ediliyor…':'Tahsilat iptalini onayla'}</button></div></form></section></div>}
  {opened&&<div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="collection-title"><div className="panel-head"><h2 id="collection-title">Tahsilat ekle</h2><button className="secondary" disabled={busy} onClick={()=>setOpened(false)}>Kapat</button></div><form onSubmit={submit}>
   <label>Müşteri<select aria-label="Tahsilat müşterisi" name="customer_id" defaultValue={filter} required disabled={busy}><option value="">Müşteri seçin</option>{balances.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
   <label>Tutar (₺)<input name="amount" type="number" required min="0.01" max="10000000" step="0.01" disabled={busy}/></label>
   <label>Tahsilat yöntemi<select aria-label="Tahsilat yöntemi" name="method" defaultValue="cash" disabled={busy}>{Object.entries(methods).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   <label>Açıklama (isteğe bağlı)<input name="note" maxLength={300} disabled={busy}/></label>
   <p className="order-help">Kayıt bugünün İstanbul tarihiyle eklenir. Borçtan fazla tahsilat müşterinin alacağı olarak görünür.</p>
   {error&&<div className="error" role="alert">{error}</div>}
   <div className="form-actions"><button className="secondary" type="button" disabled={busy} onClick={()=>setOpened(false)}>Vazgeç</button><button className="primary" disabled={busy}>{busy?'Kaydediliyor…':'Tahsilatı kaydet'}</button></div>
  </form></section></div>}
 </>;
}
