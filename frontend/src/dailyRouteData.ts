import type {MapCustomer} from './customerMapData';

export function istanbulWeekday(value=new Date()):number {
 const name=new Intl.DateTimeFormat('en-US',{timeZone:'Europe/Istanbul',weekday:'short'}).format(value);
 return ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(name)+1;
}

export function dailyRouteCustomers(customers:MapCustomer[],weekday:number):MapCustomer[]{
 if(!Number.isInteger(weekday)||weekday<1||weekday>7)return [];
 return customers.filter(customer=>customer.route_days?.includes(weekday));
}

export function unassignedRouteCustomers(customers:MapCustomer[]):MapCustomer[]{
 return customers.filter(customer=>!customer.route_days?.length);
}

export function routeDayCounts(customers:MapCustomer[]):number[]{
 return Array.from({length:7},(_,index)=>dailyRouteCustomers(customers,index+1).length);
}

export function istanbulDate(value=new Date()):string {
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Istanbul',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const get=(type:string)=>parts.find(p=>p.type===type)!.value;
 return `${get('year')}-${get('month')}-${get('day')}`;
}
export function dateWeekday(value:string):number{return new Date(value+'T12:00:00Z').getUTCDay()||7;}
export function routeDateForDay(value:string,day:number):string {
 const date=new Date(value+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+day-dateWeekday(value));return date.toISOString().slice(0,10);
}
