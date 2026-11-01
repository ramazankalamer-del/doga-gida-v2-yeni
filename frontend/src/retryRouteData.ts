import type {MapCustomer} from './customerMapData';
export function retryRouteCustomers(customers:MapCustomer[],visits:{customer_id:number;visited:number}[]):MapCustomer[]{
 const completed=new Set(visits.filter(visit=>visit.visited===1).map(visit=>visit.customer_id));
 return customers.filter(customer=>!completed.has(customer.id));
}
