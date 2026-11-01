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
