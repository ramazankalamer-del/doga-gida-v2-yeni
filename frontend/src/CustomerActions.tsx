export type CustomerAction='visits'|'statement'|'sale'|'collection'|'route';
export const routeDayNames=['Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar'];
export function routeDayLabel(days:number[]|undefined){return days?.length?days.map(day=>routeDayNames[day-1]).join(', '):'Rota günü belirlenmedi';}

export default function CustomerActions({canWrite,onAction,disabled=false}:{canWrite:boolean;onAction:(action:CustomerAction)=>void;disabled?:boolean}){
 return <div className="customer-actions"><button disabled={disabled} type="button" className="secondary" onClick={()=>onAction('statement')}>Hesap ekstresi</button><button disabled={disabled} type="button" className="secondary" onClick={()=>onAction('visits')}>Ziyaret geçmişi</button>{canWrite&&<><button disabled={disabled} type="button" className="secondary" onClick={()=>onAction('sale')}>Satış yap</button><button disabled={disabled} type="button" className="secondary" onClick={()=>onAction('collection')}>Tahsilat al</button><button disabled={disabled} type="button" className="secondary" onClick={()=>onAction('route')}>Rota günü</button></>}</div>;
}
