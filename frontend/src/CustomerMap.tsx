import CustomerCardSummary from './CustomerCardSummary';
import {retryRouteCustomers} from './retryRouteData';
import RouteOrder,{useRouteOrder,orderedRouteCustomers} from './RouteOrder';
import DailyRouteSummary from './DailyRouteSummary';
import {useCustomerVisits,VisitControls,type VisitRequest} from './CustomerVisits';
import {useEffect,useMemo,useRef,useState} from 'react';
import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {LocationLink} from './CustomerLocation';
import CustomerActions,{routeDayLabel,routeDayNames,type CustomerAction} from './CustomerActions';
import {istanbulWeekday,istanbulDate,dateWeekday,routeDateForDay,dailyRouteCustomers,unassignedRouteCustomers,routeDayCounts} from './dailyRouteData';
import {filterMapCustomers,groupMapCustomers,hasCoordinates,type MapCustomer,type LocatedCustomer,type LocationFilter} from './customerMapData';

function CustomerMapCanvas({customers,selectedId,onSelect,label}:{customers:LocatedCustomer[];selectedId:number|null;onSelect:(id:number)=>void;label:string}){
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
  <div ref={container} className="customer-map-canvas" role="region" aria-label={label}/>
  {tileError&&<div className="map-tile-error" role="alert">Bazı harita görselleri yüklenemedi. Müşteri listesi ve koordinatlar kullanılabilir. <button className="secondary" onClick={()=>{setTileError(false);tiles.current?.redraw();}}>Haritayı yeniden yükle</button></div>}
 </div>;
}

export default function CustomerMap({customers,loading,error,canWrite,onEdit,onAction,onRetry,mode='all',request}:{customers:MapCustomer[];loading:boolean;error:string;canWrite:boolean;onEdit:(customer:MapCustomer)=>void;onAction:(action:CustomerAction,customer:MapCustomer)=>void;onRetry:()=>void;mode?:'all'|'daily';request:VisitRequest}){
 const [query,setQuery]=useState(''),[filter,setFilter]=useState<LocationFilter>('all'),[selectedId,setSelectedId]=useState<number|null>(null);
 const [mapVersion,setMapVersion]=useState(0);
 const [weekday,setWeekday]=useState(istanbulWeekday),[unassigned,setUnassigned]=useState(false);
 const [visitDate,setVisitDate]=useState(istanbulDate),[visitFilter,setVisitFilter]=useState('all');
 const daily=mode==='daily';
 const [retryMode,setRetryMode]=useState(false);
 const retryActive=daily&&retryMode&&!unassigned;
 const tracker=useCustomerVisits(visitDate,daily,request);
 const completed=new Set(tracker.visits.filter(v=>v.visited).map(v=>v.customer_id));
 const dayCounts=useMemo(()=>routeDayCounts(customers),[customers]);
 const noRoute=useMemo(()=>unassignedRouteCustomers(customers),[customers]);
 const rawScope=useMemo(()=>daily?(unassigned?noRoute:dailyRouteCustomers(customers,weekday)):customers,[daily,unassigned,noRoute,customers,weekday]);
 const order=useRouteOrder(unassigned?0:weekday,daily,JSON.stringify(rawScope.map(c=>c.id).sort((a,b)=>a-b)),request);
 const [ordering,setOrdering]=useState(false);
 const scope=useMemo(()=>daily?orderedRouteCustomers(rawScope,order.data?.customer_ids??[]):rawScope,[daily,rawScope,order.data]);
 const sequencePositions=useMemo(()=>new Map(scope.map((customer,index)=>[customer.id,index+1])),[scope]);
 function chooseDay(day:number){setVisitDate(routeDateForDay(visitDate,day));setWeekday(day);setVisitFilter('all');setUnassigned(false);setSelectedId(null);setQuery('');setFilter('all');}
 const scopeName=unassigned?'Rota günü atanmayanlar':routeDayNames[weekday-1];
 const heading=retryActive?'Tekrar ziyaret listesi':daily?'Günlük rota':'Müşteri haritası';
 const pending=useMemo(()=>retryRouteCustomers(scope,tracker.visits),[scope,tracker.visits]);
 const visitById=useMemo(()=>new Map(tracker.visits.map(visit=>[visit.customer_id,visit])),[tracker.visits]);
 const filtered=useMemo(()=>filterMapCustomers(retryActive?pending:scope,query,filter).filter(c=>!daily||retryActive||visitFilter==='all'||(visitFilter==='visited'?completed.has(c.id):!completed.has(c.id))),[scope,pending,retryActive,query,filter,daily,visitFilter,tracker.visits]);
 const located=useMemo(()=>filtered.filter(hasCoordinates),[filtered]);
 const totalLocated=scope.filter(hasCoordinates).length;
 const selected=filtered.find(c=>c.id===selectedId)??null;
 return <>
  <div className="page-heading"><div><span className="eyebrow">SAHA GÖRÜNÜMÜ</span><h1>{heading}<span>.</span></h1><p>{daily?'Haftalık ziyaret günlerine göre müşterilerinizi planlayın.':'Kayıtlı GPS noktalarından müşterilerinizi bulun.'}</p></div><button className="secondary" disabled={loading} onClick={onRetry}>Listeyi yenile</button></div>
  {error&&<div className="error" role="alert">{error}<button onClick={onRetry}>Tekrar dene</button></div>}
  {loading?<p className="loading" role="status">Müşteri konumları yükleniyor…</p>:!error&&<>
   {daily&&<section className="route-planner panel" aria-label="Haftalık rota seçimi"><div className="route-planner-head"><div><h2>{scopeName}</h2><p>Birden fazla rota günü olan müşteri seçili günlerin her birinde görünür.</p></div><button className="secondary" onClick={()=>{setVisitDate(istanbulDate());setWeekday(istanbulWeekday());setUnassigned(false);setVisitFilter('all');setSelectedId(null);setQuery('');setFilter('all');setMapVersion(v=>v+1);}}>Bugünün rotası</button></div><form key={visitDate} className="visit-date" onSubmit={e=>{e.preventDefault();const value=String(new FormData(e.currentTarget).get('visit_date'));if(/^\d{4}-\d{2}-\d{2}$/.test(value)){setVisitDate(value);setWeekday(dateWeekday(value));setUnassigned(false);setSelectedId(null);setVisitFilter('all');}}}><label>Ziyaret tarihi<input name="visit_date" type="date" defaultValue={visitDate} required/></label><button className="secondary" type="submit">Tarihi göster</button></form><p className="order-help">Ziyaret durumu seçili tarihe kaydedilir. Müşteri listesi güncel haftalık plana göredir.</p><div className="route-day-buttons" role="group" aria-label="Rota günü seçin">{routeDayNames.map((name,index)=><button key={name} className={!unassigned&&weekday===index+1?'route-day-button active':'route-day-button'} aria-pressed={!unassigned&&weekday===index+1} onClick={()=>chooseDay(index+1)}><span>{name}</span><strong>{dayCounts[index]}</strong><small>müşteri</small></button>)}</div><button className="route-unassigned" aria-pressed={unassigned} onClick={()=>{setRetryMode(false);setUnassigned(true);setSelectedId(null);setQuery('');setFilter('all');}}>Günü atanmayan müşteriler ({noRoute.length})</button></section>}
   {daily&&<DailyRouteSummary key={visitDate+':'+unassigned} date={visitDate} unassigned={unassigned} request={request} refreshToken={JSON.stringify([customers.map(c=>[c.id,c.version,c.route_days]),tracker.visits.map(v=>[v.customer_id,v.version])])}/>}
   {daily&&<section className="panel visit-summary" aria-label="Ziyaret takibi"><strong>{visitDate}</strong>{tracker.loading?<p role="status">Ziyaretler yükleniyor…</p>:null}{!retryActive&&<label>Ziyaret durumu<select value={visitFilter} disabled={tracker.loading||!!tracker.error} onChange={e=>{setVisitFilter(e.target.value);setSelectedId(null);}}><option value="all">Tüm ziyaretler</option><option value="visited">Ziyaret edildi</option><option value="pending">Ziyaret edilmedi</option></select></label>}<button className="secondary" disabled={tracker.loading||tracker.busy} onClick={tracker.reload}>Ziyaretleri yenile</button>{tracker.error&&<p className="error" role="alert">{tracker.error}</p>}{visitDate>istanbulDate()&&<p>Gelecek tarih için ziyaret kaydedilemez.</p>}</section>}
   {daily&&<section className="panel retry-route-panel" aria-label="Tekrar ziyaret görünümü"><button className="secondary" aria-pressed={retryActive} disabled={!retryActive&&(tracker.loading||!!tracker.error)} onClick={()=>{setRetryMode(!retryActive);setUnassigned(false);setVisitFilter('all');setQuery('');setFilter('all');setSelectedId(null);}}>{retryActive?'Tüm rotaya dön':'Tekrar ziyaret listesi'}</button>{retryActive&&<><h2>Tekrar ziyaret edilecek müşteriler</h2><p>{visitDate} · {scopeName} · {tracker.loading?'Ziyaretler yükleniyor…':tracker.error?'Ziyaret bilgileri alınamadı.':`${pending.length} müşteri`}</p><p className="order-help">Seçilen tarihte ziyaret edildi kaydı olmayan tüm rota müşterileri dahildir. Henüz kayıt girilmemiş müşteriler de gösterilir. Ziyaret edildi kaydedilen müşteri bu listeden çıkar.</p></>}</section>}
   {daily&&<div className="route-order-toolbar">{order.loading?<p role="status">Müşteri sırası yükleniyor…</p>:order.error?<p className="error" role="alert">{order.error}<button className="secondary" onClick={order.reload}>Sıralamayı yeniden yükle</button></p>:<p>Liste kayıtlı rota sırasındadır. Yeni müşteriler sona eklenir.</p>}{canWrite&&<button className="secondary" disabled={order.loading||!!order.error||!order.data||scope.length<2} onClick={()=>setOrdering(true)}>Müşteri sırasını düzenle</button>}</div>}
   <div className="map-summary"><span><strong>{scope.length}</strong> {daily?(unassigned?'günü atanmayan müşteri':scopeName+' müşterisi'):'müşteri'}</span><span><strong>{totalLocated}</strong> GPS kayıtlı</span><span><strong>{scope.length-totalLocated}</strong> konum eksik</span></div>
   {retryActive&&(tracker.loading||tracker.error)?<section className="panel retry-route-panel"><p role={tracker.error?'alert':'status'}>{tracker.error?'Tekrar ziyaret listesi yüklenemedi. Ziyaretleri yenileyin.':'Tekrar ziyaret listesi yükleniyor…'}</p></section>:<section className="panel customer-map-panel">
    <div className="map-toolbar"><label>Müşteri veya bölge ara<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Firma, yetkili veya ilçe…"/></label><label>Konum durumu<select value={filter} onChange={e=>{setFilter(e.target.value as LocationFilter);setSelectedId(null);}}><option value="all">Tüm müşteriler</option><option value="located">GPS kayıtlı</option><option value="missing">Konum eksik</option></select></label><button className="secondary" onClick={()=>{setQuery('');setFilter('all');setSelectedId(null);setMapVersion(v=>v+1);}}>{daily?'Seçili rotayı göster':'Tüm konumları göster'}</button></div>
    <div className="customer-map-layout"><div className="map-visual">
     {located.length?<CustomerMapCanvas key={mapVersion} customers={located} selectedId={selected?.id??null} onSelect={setSelectedId} label={daily?'Günlük rota haritası':'Müşteri konum haritası'}/>:<div className="map-empty"><strong>{customers.length===0?'Henüz müşteri yok.':daily&&scope.length===0?(unassigned?'Rota günü atanmayan müşteri yok.':scopeName+' için müşteri atanmadı.'):retryActive&&pending.length===0?'Bu gün için tekrar ziyaret edilecek müşteri kalmadı.':filtered.length===0?'Aramanıza uygun müşteri bulunamadı.':'Bu görünümde GPS kaydı olan müşteri yok.'}</strong><p>{retryActive&&pending.length===0?'Başka bir gün seçebilir veya tüm rotaya dönebilirsiniz.':customers.length?(daily&&scope.length===0&&unassigned?'Müşterilerinizi gün düğmelerinden görüntüleyebilirsiniz.':daily&&scope.length===0?'Günü atanmayan müşterileri görüntüleyip Rota günü kısayolundan ziyaret günlerini belirleyebilirsiniz.':'Konum eklemek için listeden müşteri seçin ve müşteri kartını düzenleyin.'):'Müşteriler ekranından ilk müşteri kaydınızı ekleyebilirsiniz.'}</p></div>}
     {located.length>0&&<p className="map-caption">{located.length} müşteri haritada. Aynı GPS noktasındaki müşteriler tek işarette gruplanır. Görüntülenen bölgenin harita görselleri OpenStreetMap’ten yüklenir; internet bağlantısı gerekir.</p>}
    </div><aside className="map-customer-list" aria-label={daily?'Rota müşteri listesi':'Harita müşteri listesi'}>
     <div className="map-list-title"><h2>{retryActive?'Tekrar ziyaret edilecekler':daily?'Rota müşterileri':'Müşteriler'}</h2><span className="count">{filtered.length} kayıt</span></div>
     {selected&&<section className="map-selected" aria-label="Seçilen müşteri bilgileri"><h3>{selected.name}</h3><p>{selected.contact} · {selected.district}</p><p>{selected.phone||'Telefon belirtilmedi'}</p><p>{routeDayLabel(selected.route_days)}</p><CustomerCardSummary key={selected.id+':'+selected.version+':'+(visitById.get(selected.id)?.version??0)} customer={selected} request={request}/>{daily&&(tracker.loading?<p>Ziyaret durumu henüz alınamadı.</p>:<VisitControls key={selected.id+':'+visitDate+':'+(tracker.visits.find(v=>v.customer_id===selected.id)?.version??0)} visit={tracker.visits.find(v=>v.customer_id===selected.id)} disabled={!canWrite||tracker.loading||tracker.busy||!!tracker.error||visitDate>istanbulDate()} onSave={(value,note,reason)=>tracker.save(selected.id,value,note,reason)}/> )}<CustomerActions canWrite={canWrite} onAction={action=>onAction(action,selected)}/><LocationLink latitude={selected.latitude} longitude={selected.longitude}/>{canWrite&&<button className="secondary" onClick={()=>onEdit(selected)}>Müşteri kartını düzenle</button>}<button className="text-button" onClick={()=>setSelectedId(null)}>Seçimi kaldır</button></section>}
     <div className="map-list-scroll">{filtered.map(customer=><button key={customer.id} className={'map-customer-row'+(selected?.id===customer.id?' selected':'')} aria-pressed={selected?.id===customer.id} onClick={()=>setSelectedId(customer.id)}><strong>{daily?`${sequencePositions.get(customer.id)}. `:''}{customer.name}</strong><span>{customer.district} · {customer.contact}</span>{retryActive&&<span className="retry-visit-detail">{visitById.has(customer.id)?<><span>Ziyaret notu: {visitById.get(customer.id)?.note||'Not eklenmedi.'}</span><span>Edilememe nedeni: {visitById.get(customer.id)?.reason||'Neden belirtilmedi.'}</span></>:<span>Henüz ziyaret kaydı girilmedi.</span>}</span>}{daily&&<><span>{routeDayLabel(customer.route_days)}</span><span>{tracker.loading?'Ziyaret durumu yükleniyor':tracker.error?'Ziyaret durumu alınamadı':completed.has(customer.id)?'Ziyaret edildi':'Ziyaret edilmedi'}</span></>}<small className={'badge '+(hasCoordinates(customer)?'green':'amber')}>{hasCoordinates(customer)?'GPS kayıtlı':'Konum eksik'}</small></button>)}</div>
     {!filtered.length&&<p className="empty">{retryActive&&pending.length===0?'Seçili günün rotasında tekrar ziyaret edilecek müşteri yok.':'Gösterilecek müşteri yok.'}</p>}
    </aside></div>
   </section>}
  </>}
 {ordering&&order.data&&<RouteOrder key={order.data.scope_id} customers={rawScope} data={order.data} label={scopeName} request={request} onClose={()=>setOrdering(false)} onSaved={order.apply} onReload={()=>{setOrdering(false);order.reload();onRetry();}}/>}
 </>;
}
