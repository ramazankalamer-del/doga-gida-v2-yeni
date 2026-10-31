import { useEffect, useState, type FormEvent } from 'react';

type WarehouseCode = 'MERKEZ'|'IADE';
type Product = {id:number;name:string;sku:string;stock:number;return_stock:number};
type Data = {warehouses:{code:WarehouseCode;name:string;sellable:boolean;stock:number}[];products:Product[]};
type Request = <T>(path:string,data?:object)=>Promise<T>;

export default function Warehouses({request,canWrite,onSaved}:{request:Request;canWrite:boolean;onSaved:()=>Promise<void>}) {
 const [data,setData]=useState<Data|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [mode,setMode]=useState<'return'|'transfer'|null>(null),[busy,setBusy]=useState(false),[requestId,setRequestId]=useState('');
 const [source,setSource]=useState<WarehouseCode>('IADE'),[filter,setFilter]=useState('');
 async function load(){setData(await request<Data>('warehouses'));}
 useEffect(()=>{void load().catch(e=>setError((e as Error).message));},[]);
 useEffect(()=>{if(!mode)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!busy)setMode(null);};document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close);},[mode,busy]);
 function open(next:'return'|'transfer'){setMode(next);setRequestId(crypto.randomUUID());setError('');setNotice('');setSource('IADE');}
 async function submit(e:FormEvent<HTMLFormElement>){
  e.preventDefault();const values=Object.fromEntries(new FormData(e.currentTarget));setBusy(true);setError('');
  try{
   await request(mode==='return'?'warehouse-returns':'warehouse-transfers',{
    product_id:Number(values.product_id),quantity:Number(values.quantity),note:values.note,request_id:requestId,
    ...(mode==='transfer'?{source,target:source==='IADE'?'MERKEZ':'IADE',inspection_confirmed:values.inspection==='on'}:{})
   });
  }catch(e){setError((e as Error).message);setBusy(false);return;}
  setMode(null);setNotice('Depo işlemi kaydedildi.');
  try{await load();await onSaved();}catch{setError('İşlem kaydedildi; güncel liste yüklenemedi. Sayfayı yenileyin.');}finally{setBusy(false);}
 }
 return <section className="warehouse-section" aria-label="Depo yönetimi">
  <div className="panel-head"><div><h2>Depolar</h2><p>Satışlar yalnızca Merkez Depo stoğunu kullanır.</p></div>{canWrite&&<div className="warehouse-actions"><button className="secondary" disabled={!data||busy} onClick={()=>open('return')}>İade kabul et</button><button className="primary" disabled={!data||busy} onClick={()=>open('transfer')}>Depolar arası transfer</button></div>}</div>
  {notice&&<div className="notice" role="status">{notice}</div>}{error&&!mode&&<div className="error" role="alert">{error}<button onClick={()=>void load().then(()=>setError('')).catch(e=>setError((e as Error).message))}>Yeniden yükle</button></div>}
  {!data?<p role="status">Depolar yükleniyor…</p>:<><div className="warehouse-cards">{data.warehouses.map(w=><article className="panel warehouse-card" key={w.code}><span className={'badge '+(w.sellable?'green':'amber')}>{w.sellable?'Satılabilir stok':'Kontrol bekleyen stok'}</span><h3>{w.name}</h3><strong>{w.stock.toLocaleString('tr-TR')} adet</strong><p>{w.sellable?'Siparişler bu depodan karşılanır.':'Kontrol onayı olmadan satışa aktarılmaz.'}</p></article>)}</div>
   <section className="panel"><div className="panel-head"><h3>Depolara göre ürün stokları</h3><label className="search"><input aria-label="Depoda ürün ara" placeholder="Ürün veya kod ara…" value={filter} onChange={e=>setFilter(e.target.value)}/></label></div><div className="table-wrap"><table><thead><tr><th>ÜRÜN</th><th>MERKEZ DEPO</th><th>İADE DEPOSU</th><th>FİZİKSEL TOPLAM</th></tr></thead><tbody>{data.products.filter(p=>(p.name+' '+p.sku).toLocaleLowerCase('tr').includes(filter.toLocaleLowerCase('tr'))).map(p=><tr key={p.id}><td><strong>{p.name}</strong><small>{p.sku}</small></td><td>{p.stock} adet</td><td>{p.return_stock} adet</td><td>{p.stock+p.return_stock} adet</td></tr>)}</tbody></table>{!data.products.length&&<p className="empty">Henüz ürün yok.</p>}</div></section>
  </>}
  {mode&&data&&<div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="warehouse-title"><div className="panel-head"><h2 id="warehouse-title">{mode==='return'?'İade kabul et':'Depolar arası transfer'}</h2><button className="secondary" disabled={busy} onClick={()=>setMode(null)}>Kapat</button></div><form onSubmit={submit}>
   <p className="order-help">{mode==='return'?'Teslim alınan ürün İade Deposu’na eklenir. Bu işlem sipariş veya müşteri bakiyesini değiştirmez.':'İşlem iki deponun stoklarını birlikte günceller; fiziksel toplam değişmez.'}</p>
   {mode==='transfer'&&<label>Transfer yönü<select value={source} onChange={e=>setSource(e.target.value as WarehouseCode)} disabled={busy}><option value="IADE">İade Deposu → Merkez Depo (kontrol sonrası)</option><option value="MERKEZ">Merkez Depo → İade Deposu (kontrole ayır)</option></select></label>}
   <label>Ürün<select name="product_id" required disabled={busy} defaultValue=""><option value="">Ürün seçin</option>{data.products.map(p=><option value={p.id} key={p.id}>{p.name} · {p.sku} · Merkez {p.stock} / İade {p.return_stock}</option>)}</select></label>
   <label>Adet<input name="quantity" type="number" min="1" max="10000000" step="1" required disabled={busy}/></label>
   <label>Açıklama<input name="note" minLength={3} maxLength={300} required disabled={busy} placeholder="İade nedeni veya kontrol sonucu"/></label>
   {mode==='transfer'&&source==='IADE'&&<label className="inspection-check"><input type="checkbox" name="inspection" required disabled={busy}/>Ürünlerin kontrol edildiğini ve satışa uygun olduğunu onaylıyorum.</label>}
   {error&&<div className="error" role="alert">{error}</div>}<div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>setMode(null)}>Vazgeç</button><button className="primary" disabled={busy}>{busy?'Kaydediliyor…':'Depo işlemini kaydet'}</button></div>
  </form></section></div>}
 </section>;
}
