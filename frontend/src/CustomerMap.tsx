import {useEffect,useMemo,useRef,useState} from 'react';
import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {LocationLink} from './CustomerLocation';
import CustomerActions,{routeDayLabel,type CustomerAction} from './CustomerActions';
import {filterMapCustomers,groupMapCustomers,hasCoordinates,type MapCustomer,type LocatedCustomer,type LocationFilter} from './customerMapData';

function CustomerMapCanvas({customers,selectedId,onSelect}:{customers:LocatedCustomer[];selectedId:number|null;onSelect:(id:number)=>void}){
 const container=useRef<HTMLDivElement>(null),map=useRef<L.Map|null>(null),markers=useRef(new Map<number,L.Marker>());
 const select=useRef(onSelect);select.current=onSelect;
 const [tileError,setTileError]=useState(false);
 const tiles=useRef<L.TileLayer|null>(null);
 const groups=useMemo(()=>groupMapCustomers(customers),[customers]);
 useEffect(()=>{
  if(!container.current)return;
  const instance=L.map(container.current,{zoomControl:false,scrollWheelZoom:false}).setView([39,35],6);
  map.current=instance;
  L.control.zoom({zoomInTitle:'Yakınlaştır',zoomOutTitle:'Uzaklaştır'}).addTo(instance);
  const url=(import.meta as ImportMeta & {env?:Record<string,string>}).env?.VITE_MAP_TILE_URL||'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  const tileLayer=L.tileLayer(url,{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> katkıda bulunanlar'}).addTo(instance);
  tiles.current=tileLayer;
  tileLayer.on('tileerror',()=>setTileError(true));
  const observer=new ResizeObserver(()=>instance.invalidateSize());observer.observe(container.current);
  return()=>{observer.disconnect();instance.remove();map.current=null;tiles.current=null;markers.current.clear();};
 },[]);
 useEffect(()=>{
  const instance=map.current;if(!instance)return;
  const layer=L.layerGroup().addTo(instance);markers.current.clear();
  for(const group of groups){
   const first=group[0];
   // Text nodes keep customer-provided names out of Leaflet's HTML parser.
   const popup=document.createElement('div');popup.className='customer-map-popup';
   const heading=document.createElement('strong');heading.textContent=group.length>1?`${group.length} müşteri aynı konumda`:first.name;popup.append(heading);
   for(const customer of group){
    const button=document.createElement('button');button.type='button';button.textContent=group.length>1?customer.name:'Müşteri bilgilerini göster';
    button.addEventListener('click',()=>select.current(customer.id));popup.append(button);
   }
   const marker=L.marker([first.latitude,first.longitude],{
    icon:L.divIcon({className:'customer-map-pin',html:group.length>1?`<span>${group.length}</span>`:'<span aria-hidden="true">●</span>',iconSize:[32,32],iconAnchor:[16,16]}),
    title:group.length>1?`${group.length} müşteri aynı konumda`:first.name,alt:'Müşteri konumu',keyboard:true
   }).addTo(layer).bindPopup(popup);
   marker.on('click',()=>select.current(first.id));
   for(const customer of group)markers.current.set(customer.id,marker);
  }
  const points=groups.map(group=>L.latLng(group[0].latitude,group[0].longitude));
  if(points.length)instance.fitBounds(L.latLngBounds(points),{padding:[36,36],maxZoom:14});
  return()=>{layer.remove();markers.current.clear();};
 },[groups]);
 useEffect(()=>{
  if(selectedId===null){map.current?.closePopup();return;}
  const marker=markers.current.get(selectedId);
  if(marker&&map.current){map.current.panTo(marker.getLatLng());marker.openPopup();}
  else map.current?.closePopup();
 },[selectedId,groups]);
 return <div className="customer-map-canvas-wrap">
  <div ref={container} className="customer-map-canvas" role="region" aria-label="Müşteri konum haritası"/>
  {tileError&&<div className="map-tile-error" role="alert">Bazı harita görselleri yüklenemedi. Müşteri listesi ve koordinatlar kullanılabilir. <button className="secondary" onClick={()=>{setTileError(false);tiles.current?.redraw();}}>Haritayı yeniden yükle</button></div>}
 </div>;
}

export default function CustomerMap({customers,loading,error,canWrite,onEdit,onAction,onRetry}:{customers:MapCustomer[];loading:boolean;error:string;canWrite:boolean;onEdit:(customer:MapCustomer)=>void;onAction:(action:CustomerAction,customer:MapCustomer)=>void;onRetry:()=>void}){
 const [query,setQuery]=useState(''),[filter,setFilter]=useState<LocationFilter>('all'),[selectedId,setSelectedId]=useState<number|null>(null);
 const [mapVersion,setMapVersion]=useState(0);
 const filtered=useMemo(()=>filterMapCustomers(customers,query,filter),[customers,query,filter]);
 const located=useMemo(()=>filtered.filter(hasCoordinates),[filtered]);
 const totalLocated=customers.filter(hasCoordinates).length;
 const selected=filtered.find(c=>c.id===selectedId)??null;
 return <>
  <div className="page-heading"><div><span className="eyebrow">SAHA GÖRÜNÜMÜ</span><h1>Müşteri haritası<span>.</span></h1><p>Kayıtlı GPS noktalarından müşterilerinizi bulun.</p></div><button className="secondary" disabled={loading} onClick={onRetry}>Listeyi yenile</button></div>
  {error&&<div className="error" role="alert">{error}<button onClick={onRetry}>Tekrar dene</button></div>}
  {loading?<p className="loading" role="status">Müşteri konumları yükleniyor…</p>:!error&&<>
   <div className="map-summary"><span><strong>{customers.length}</strong> müşteri</span><span><strong>{totalLocated}</strong> GPS kayıtlı</span><span><strong>{customers.length-totalLocated}</strong> konum eksik</span></div>
   <section className="panel customer-map-panel">
    <div className="map-toolbar"><label>Müşteri veya bölge ara<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Firma, yetkili veya ilçe…"/></label><label>Konum durumu<select value={filter} onChange={e=>{setFilter(e.target.value as LocationFilter);setSelectedId(null);}}><option value="all">Tüm müşteriler</option><option value="located">GPS kayıtlı</option><option value="missing">Konum eksik</option></select></label><button className="secondary" onClick={()=>{setQuery('');setFilter('all');setSelectedId(null);setMapVersion(v=>v+1);}}>Tüm konumları göster</button></div>
    <div className="customer-map-layout"><div className="map-visual">
     {located.length?<CustomerMapCanvas key={mapVersion} customers={located} selectedId={selected?.id??null} onSelect={setSelectedId}/>:<div className="map-empty"><strong>{customers.length===0?'Henüz müşteri yok.':filtered.length===0?'Aramanıza uygun müşteri bulunamadı.':'Bu görünümde GPS kaydı olan müşteri yok.'}</strong><p>{customers.length?'Konum eklemek için listeden müşteri seçin ve müşteri kartını düzenleyin.':'Müşteriler ekranından ilk müşteri kaydınızı ekleyebilirsiniz.'}</p></div>}
     {located.length>0&&<p className="map-caption">{located.length} müşteri haritada. Aynı GPS noktasındaki müşteriler tek işarette gruplanır. Görüntülenen bölgenin harita görselleri OpenStreetMap’ten yüklenir; internet bağlantısı gerekir.</p>}
    </div><aside className="map-customer-list" aria-label="Harita müşteri listesi">
     <div className="map-list-title"><h2>Müşteriler</h2><span className="count">{filtered.length} kayıt</span></div>
     {selected&&<section className="map-selected" aria-label="Seçilen müşteri bilgileri"><h3>{selected.name}</h3><p>{selected.contact} · {selected.district}</p><p>{selected.phone||'Telefon belirtilmedi'}</p><p>{routeDayLabel(selected.route_days)}</p><CustomerActions canWrite={canWrite} onAction={action=>onAction(action,selected)}/><LocationLink latitude={selected.latitude} longitude={selected.longitude}/>{canWrite&&<button className="secondary" onClick={()=>onEdit(selected)}>Müşteri kartını düzenle</button>}<button className="text-button" onClick={()=>setSelectedId(null)}>Seçimi kaldır</button></section>}
     <div className="map-list-scroll">{filtered.map(customer=><button key={customer.id} className={'map-customer-row'+(selected?.id===customer.id?' selected':'')} aria-pressed={selected?.id===customer.id} onClick={()=>setSelectedId(customer.id)}><strong>{customer.name}</strong><span>{customer.district} · {customer.contact}</span><small className={'badge '+(hasCoordinates(customer)?'green':'amber')}>{hasCoordinates(customer)?'GPS kayıtlı':'Konum eksik'}</small></button>)}</div>
     {!filtered.length&&<p className="empty">Gösterilecek müşteri yok.</p>}
    </aside></div>
   </section>
  </>}
 </>;
}
