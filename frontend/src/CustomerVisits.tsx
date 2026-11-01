import {useEffect,useRef,useState} from 'react';
export type Visit={customer_id:number;visit_date:string;visited:number;version:number;updated_username:string;updated_at:string};
export type VisitRequest=<T>(path:string,data?:object)=>Promise<T>;
export function useCustomerVisits(date:string,enabled:boolean,request:VisitRequest){
 const [visits,setVisits]=useState<Visit[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const generation=useRef(0);
 useEffect(()=>{const id=++generation.current;setVisits([]);setError('');setBusy(false);if(!enabled){setLoading(false);return;}setLoading(true);
 request<Visit[]>(`customer-visits?visit_date=${date}`).then(rows=>{if(id===generation.current)setVisits(rows);}).catch(e=>{if(id===generation.current)setError((e as Error).message);}).finally(()=>{if(id===generation.current)setLoading(false);});
 return()=>{generation.current++;};},[date,enabled,request,revision]);
 async function save(customerId:number,visited:boolean){const id=generation.current;setBusy(true);setError('');try{
 const row=await request<Visit>(`customers/${customerId}/visit`,{visit_date:date,visited,expected_version:visits.find(v=>v.customer_id===customerId)?.version??0});
 if(id===generation.current)setVisits(old=>[...old.filter(v=>v.customer_id!==customerId),row]);
 }catch(e){if(id===generation.current)setError((e as Error).message);}finally{if(id===generation.current)setBusy(false);}}
 return {visits,loading,error,busy,save,reload:()=>setRevision(v=>v+1)};
}
export function VisitControls({visit,disabled,onSave}:{visit?:Visit;disabled:boolean;onSave:(visited:boolean)=>void}){
 return <div className="visit-controls"><strong>{visit?.visited?'Ziyaret edildi':'Ziyaret edilmedi'}</strong>{visit&&<small>Son kayıt: {visit.updated_username} · {new Date(visit.updated_at).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'})}</small>}<div><button className="secondary" disabled={disabled||!!visit?.visited} onClick={()=>onSave(true)}>Ziyaret edildi</button><button className="secondary" disabled={disabled||!visit?.visited} onClick={()=>onSave(false)}>Ziyaret edilmedi</button></div></div>;
}
