import { useEffect, useRef, useState } from 'react';
import { captureLocation } from './location';

export type Coordinates = {latitude:number|null;longitude:number|null};

export function LocationLink({latitude,longitude}:Coordinates){
 if(latitude===null||longitude===null||latitude===undefined||longitude===undefined)return <span>Konum eklenmedi</span>;
 const url=`https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`;
 return <><a href={url} target="_blank" rel="noopener noreferrer">Haritada aç ↗</a><small>{latitude.toFixed(6)}, {longitude.toFixed(6)}</small></>;
}

export default function CustomerLocation({initial,disabled,onLocating}:{initial?:Coordinates;disabled:boolean;onLocating:(busy:boolean)=>void}){
 const [latitude,setLatitude]=useState(initial?.latitude?.toString()??'');
 const [longitude,setLongitude]=useState(initial?.longitude?.toString()??'');
 const [locating,setLocating]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const active=useRef(true);
 useEffect(()=>{active.current=true;return()=>{active.current=false;onLocating(false);};},[onLocating]);
 async function locate(){
  setMessage('');setError('');
  setLocating(true);onLocating(true);
  try{
   const result=await captureLocation(navigator.geolocation,window.isSecureContext);
   if(!active.current)return;
   setLatitude(result.latitude);setLongitude(result.longitude);
   setMessage(`Konum alındı${result.accuracy!==null?` · yaklaşık doğruluk: ${result.accuracy} metre`:''}. Kaydetmeden önce kontrol edin.`);
  }catch(e){if(active.current)setError((e as Error).message);}finally{if(active.current){setLocating(false);onLocating(false);}}
 }
 return <fieldset className="gps-fields" disabled={disabled}><legend>GPS konumu (isteğe bağlı)</legend><p className="order-help">Müşterinin enlem ve boylamını birlikte girin. Ondalık koordinat kullanın; örnek: 41.008200 / 28.978400.</p>
  <button type="button" className="secondary" disabled={disabled||locating} onClick={locate}>{locating?'Konum alınıyor…':'Konumumu al'}</button>
  <p className="order-help">Müşterinin yanındayken kullanın. Bu buton müşterinin değil, kullandığınız cihazın o anki konumunu alır. Tarayıcı izin isteyebilir; arka planda takip yapılmaz.</p>
  {message&&<p className="notice" role="status">{message}</p>}{error&&<p className="error" role="alert">{error}</p>}
  <div className="form-row"><label>Enlem<input name="latitude" type="number" min="-90" max="90" step="any" value={latitude} disabled={locating} onChange={e=>{setLatitude(e.target.value);setMessage('');}} required={longitude!==''} placeholder="41.008200"/></label>
  <label>Boylam<input name="longitude" type="number" min="-180" max="180" step="any" value={longitude} disabled={locating} onChange={e=>{setLongitude(e.target.value);setMessage('');}} required={latitude!==''} placeholder="28.978400"/></label></div>
  <button type="button" className="secondary" disabled={disabled||locating||(latitude===''&&longitude==='')} onClick={()=>{setLatitude('');setLongitude('');setMessage('');}}>GPS bilgisini temizle</button>
  <p className="order-help">Ekleme, değişiklik ve temizleme işlemi Kaydet düğmesine bastığınızda uygulanır. Konum yalnızca Haritada aç bağlantısını seçtiğinizde harita sitesine gönderilir.</p>
 </fieldset>;
}
